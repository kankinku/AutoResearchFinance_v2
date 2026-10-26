"""Read-only honest classification of experimental Codex cohorts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from application.python_mcp_research_audit import audit_python_mcp_cohort
from core.data.contracts import Bar, DataZone, MarketDataSet
from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash


def _study(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    work = root / "state/python-mcp/experiment"
    work.mkdir(parents=True)
    session = "a" * 32
    data = MarketDataSet(
        "v1",
        DataZone.DEVELOPMENT,
        (Bar(datetime(2020, 1, 2, tzinfo=timezone.utc), "QQQ", 100, 103, 99, 102, 1000),),
    )
    parquet = work / "qqq-development-nonpit-2020-2025.parquet"
    ParquetDataProvider.write(parquet, data)
    (work / "session.json").write_text(
        json.dumps(
            {
                "session_id": session,
                "generations": 2,
                "scope": "REAL_MODEL_NON_PIT_UNATTESTED_EXPERIMENT_ONLY",
                "dataset_sha256": hashlib.sha256(parquet.read_bytes()).hexdigest(),
            }
        )
    )
    folder = work / "checkpoint/academic-gpt-checkpoints"
    folder.mkdir(parents=True)
    with sqlite3.connect(folder / "cycles.sqlite") as db:
        db.execute(
            "create table sessions(id text, requested integer, completed integer, "
            "status text, dataset_hash text)"
        )
        db.execute(
            "create table generations(session_id text, generation integer, "
            "evidence_json text, evidence_hash text)"
        )
        db.execute(
            "insert into sessions values(?,?,?,?,?)",
            (session, 2, 2, "COMPLETED", data.dataset_hash),
        )
        previous = None
        for i in (1, 2):
            ev = {
                "generation": i,
                "previous_evidence_hash": previous,
                "dataset_hash": data.dataset_hash,
                "independent_oos_approved": False,
                "broker_executable": False,
                "metrics": {"total_return": 0.2 * i, "max_drawdown": 0.1, "trade_count": 32},
                "experiments": [{"hypothesis_id": f"h{i}"}],
                "analysis_summary": "test",
            }
            h = content_hash(
                {
                    "schema": "external-gpt-academic-generation-v1",
                    "session_id": session,
                    "generation": i,
                    "previous_hash": previous,
                    "payload": ev,
                }
            )
            db.execute("insert into generations values(?,?,?,?)", (session, i, json.dumps(ev), h))
            previous = h
    with (work / "model-audit.jsonl").open("w") as f:
        for i in (1, 2):
            for stage in ("plan", "diagnosis"):
                meta = {
                    "host": "Codex SDK",
                    "thread_id": f"thread-{i}-{stage}",
                    "turn_id": f"turn-{i}-{stage}",
                    "auth_provenance": "UNVERIFIED_LOCAL_SDK_METADATA",
                    "independent_model_invocation_verified": False,
                    "token_usage": {"total_tokens": 500},
                }
                for event in ("MODEL_OUTPUT", "CANONICAL_ACCEPTED"):
                    f.write(
                        json.dumps(
                            {
                                "event": event,
                                "stage": stage,
                                "generation": i,
                                "model_metadata": meta,
                            }
                        )
                        + "\n"
                    )
    return root, work


def test_two_generation_audit_does_not_claim_provider_attestation(tmp_path: Path):
    root, work = _study(tmp_path)
    result = audit_python_mcp_cohort(root, work)
    assert result["completed_generations"] == 2
    assert result["linked_evidence_verified"]
    assert result["provider_invocation_independently_verified"] is False
    assert result["model_sdk_output_events"] == 4
    assert result["max_return_generation"] == 2
    assert result["missing_canonical_acceptance_markers"] == []
    assert result["orders_enabled"] is False


def test_tampered_evidence_rejected(tmp_path: Path):
    root, work = _study(tmp_path)
    path = work / "checkpoint/academic-gpt-checkpoints/cycles.sqlite"
    with sqlite3.connect(path) as db:
        ev = json.loads(
            db.execute("select evidence_json from generations where generation=2").fetchone()[0]
        )
        ev["metrics"]["total_return"] = 99
        db.execute("update generations set evidence_json=? where generation=2", (json.dumps(ev),))
    with pytest.raises(ValueError, match="evidence hash"):
        audit_python_mcp_cohort(root, work)


def test_missing_diagnosis_model_observation_rejected(tmp_path: Path):
    root, work = _study(tmp_path)
    p = work / "model-audit.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    p.write_text(
        "\n".join(
            json.dumps(x)
            for x in rows
            if not (
                x["generation"] == 2 and x["stage"] == "diagnosis" and x["event"] == "MODEL_OUTPUT"
            )
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="missing recorded model output"):
        audit_python_mcp_cohort(root, work)


def test_missing_acceptance_marker_is_reported_not_faked(tmp_path: Path):
    root, work = _study(tmp_path)
    p = work / "model-audit.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    p.write_text(
        "\n".join(
            json.dumps(x)
            for x in rows
            if not (
                x["generation"] == 1
                and x["stage"] == "diagnosis"
                and x["event"] == "CANONICAL_ACCEPTED"
            )
        )
        + "\n"
    )
    result = audit_python_mcp_cohort(root, work)
    assert result["missing_canonical_acceptance_markers"] == ["G1:diagnosis"]
    assert result["completed_generations"] == 2


def test_outside_state_path_rejected(tmp_path: Path):
    root, work = _study(tmp_path)
    with pytest.raises(ValueError, match="isolated fork"):
        audit_python_mcp_cohort(root, tmp_path)


def test_mutated_dataset_is_rejected(tmp_path: Path):
    root, work = _study(tmp_path)
    p = work / "qqq-development-nonpit-2020-2025.parquet"
    p.write_bytes(p.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="source data hash"):
        audit_python_mcp_cohort(root, work)


def _add_gateway(work: Path, *, valid: bool = True) -> None:
    from core.integrity.hashes import content_hash

    folder = work / "checkpoint/academic-gpt-checkpoints"
    cycles = sqlite3.connect(folder / "cycles.sqlite")
    items = cycles.execute("SELECT generation,evidence_hash FROM generations").fetchall()
    cycles.close()
    with sqlite3.connect(folder / "gateway.sqlite") as db:
        db.execute("CREATE TABLE stages (session_id text, phase text)")
        db.execute("INSERT INTO stages VALUES (?,?)", ("a" * 32, "COMPLETED"))
        db.execute(
            "CREATE TABLE generation_timings ("
            "session_id text,generation integer,start_utc text,end_utc text,evidence_hash text)"
        )
        db.execute(
            "CREATE TABLE p4_s7_approvals ("
            "session_id text,generation integer,review_json text,review_hash text)"
        )
        for generation, evidence_hash in items:
            db.execute(
                "INSERT INTO generation_timings VALUES (?,?,?,?,?)",
                (
                    "a" * 32,
                    generation,
                    "2026-10-25T12:00:00+00:00",
                    "2026-10-25T12:01:00+00:00",
                    evidence_hash,
                ),
            )
            review = {
                "generation": generation,
                "counted_evidence_hash": evidence_hash,
                "review": {"eligible": True},
            }
            if not valid and generation == 1:
                review["counted_evidence_hash"] = "f" * 64
            db.execute(
                "INSERT INTO p4_s7_approvals VALUES (?,?,?,?)",
                ("a" * 32, generation, json.dumps(review), content_hash(review)),
            )


def test_missing_diagnosis_ack_has_separate_corroboration_not_log_rewrite(tmp_path: Path):
    from application.python_mcp_checkpoint_reconciliation import reconcile_python_mcp_cohort

    root, work = _study(tmp_path)
    _add_gateway(work)
    log = work / "model-audit.jsonl"
    original = log.read_bytes()
    log.write_text(
        "\n".join(
            line
            for line in original.decode().splitlines()
            if not (
                "CANONICAL_ACCEPTED" in line
                and '"generation": 1' in line
                and '"stage": "diagnosis"' in line
            )
        )
        + "\n"
    )
    before = log.read_bytes()
    result = reconcile_python_mcp_cohort(root, work)
    assert result["missing_canonical_acceptance_markers"] == ["G1:diagnosis"]
    assert (
        result["missing_marker_corroboration"][0]["status"] == "CORROBORATED_CANONICAL_SQLITE_ONLY"
    )
    assert result["missing_marker_corroboration"][0]["provider_attested"] is False
    assert result["resume_gate"] == "NOOP_COMPLETED"
    assert log.read_bytes() == before
    assert result["new_generations"] == 0


def test_corrupt_s7_cannot_corroborate_missing_ack(tmp_path: Path):
    from application.python_mcp_checkpoint_reconciliation import reconcile_python_mcp_cohort

    root, work = _study(tmp_path)
    _add_gateway(work, valid=False)
    log = work / "model-audit.jsonl"
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    log.write_text(
        "\n".join(
            json.dumps(x)
            for x in rows
            if not (
                x["event"] == "CANONICAL_ACCEPTED"
                and x["stage"] == "diagnosis"
                and x["generation"] == 1
            )
        )
        + "\n"
    )
    result = reconcile_python_mcp_cohort(root, work)
    assert result["missing_marker_corroboration"][0]["status"] == "UNRESOLVED"
    assert result["resume_gate"] == "NOOP_COMPLETED"


def test_incomplete_session_never_auto_advance(tmp_path: Path):
    from application.python_mcp_checkpoint_reconciliation import reconcile_python_mcp_cohort

    root, work = _study(tmp_path)
    _add_gateway(work)
    gateway = work / "checkpoint/academic-gpt-checkpoints/gateway.sqlite"
    cycle = work / "checkpoint/academic-gpt-checkpoints/cycles.sqlite"
    with sqlite3.connect(cycle) as db:
        db.execute("UPDATE sessions SET requested=3, status=?", ("AWAITING_PROVIDER",))
    with sqlite3.connect(gateway) as db:
        db.execute("UPDATE stages SET phase=?", ("AWAITING_PLAN",))
    result = reconcile_python_mcp_cohort(root, work)
    assert result["resume_gate"] == "REQUIRES_AUTHENTICATED_MODEL_DECISION"
    assert result["new_generations"] == 0


def test_unexpected_checkpoint_phase_blocks_resume(tmp_path: Path):
    from application.python_mcp_checkpoint_reconciliation import reconcile_python_mcp_cohort

    root, work = _study(tmp_path)
    _add_gateway(work)
    cycle = work / "checkpoint/academic-gpt-checkpoints/cycles.sqlite"
    with sqlite3.connect(cycle) as db:
        db.execute("UPDATE sessions SET requested=3, status=?", ("EXECUTING",))
    result = reconcile_python_mcp_cohort(root, work)
    assert result["resume_gate"] == "BLOCKED_CHECKPOINT_UNCERTAIN"
    assert result["new_generations"] == 0


def test_completed_with_mismatched_gateway_phase_is_blocked(tmp_path: Path):
    from application.python_mcp_checkpoint_reconciliation import reconcile_python_mcp_cohort

    root, work = _study(tmp_path)
    _add_gateway(work)
    gateway = work / "checkpoint/academic-gpt-checkpoints/gateway.sqlite"
    with sqlite3.connect(gateway) as db:
        db.execute("UPDATE stages SET phase=?", ("AWAITING_PLAN",))
    report = reconcile_python_mcp_cohort(root, work)
    assert report["resume_gate"] == "BLOCKED_CHECKPOINT_UNCERTAIN"
    assert report["new_generations"] == 0


def test_gateway_symlink_cannot_access_another_project(tmp_path: Path):
    from application.python_mcp_checkpoint_reconciliation import reconcile_python_mcp_cohort

    root, work = _study(tmp_path)
    external = tmp_path / "external.db"
    external.touch()
    (work / "checkpoint/academic-gpt-checkpoints/gateway.sqlite").symlink_to(external)
    with pytest.raises(ValueError, match="symlinked"):
        reconcile_python_mcp_cohort(root, work)


def test_invalid_s7_review_hash_is_unresolved(tmp_path: Path):
    from application.python_mcp_checkpoint_reconciliation import reconcile_python_mcp_cohort

    root, work = _study(tmp_path)
    _add_gateway(work)
    gateway = work / "checkpoint/academic-gpt-checkpoints/gateway.sqlite"
    with sqlite3.connect(gateway) as db:
        db.execute("UPDATE p4_s7_approvals SET review_hash=? WHERE generation=1", ("0" * 64,))
    log = work / "model-audit.jsonl"
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    log.write_text(
        "\n".join(
            json.dumps(x)
            for x in rows
            if not (
                x["event"] == "CANONICAL_ACCEPTED"
                and x["stage"] == "diagnosis"
                and x["generation"] == 1
            )
        )
        + "\n"
    )
    result = reconcile_python_mcp_cohort(root, work)
    assert result["missing_marker_corroboration"][0]["status"] == "UNRESOLVED"
