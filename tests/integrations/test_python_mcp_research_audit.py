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
