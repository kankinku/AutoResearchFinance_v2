"""D02: operator-controlled crash recovery preserves the model evidence chain."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService, _SubmittedProvider
from integrations.codex_mcp_core import create_mcp_server
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _service(tmp_path: Path) -> AcademicMCPCheckpointService:
    return AcademicMCPCheckpointService(
        project_root=tmp_path / "project", state_dir=tmp_path / "state",
    )


def _simulate_gateway_crash_after_cycle_commit(
    tmp_path: Path, server: object, staged: dict,
) -> tuple[AcademicMCPCheckpointService, dict]:
    svc = _service(tmp_path)
    sid = staged["session_id"]
    with svc._connect() as db:
        row = db.execute("SELECT * FROM stages WHERE session_id=?", (sid,)).fetchone()
        assert row is not None
        plan = json.loads(row["plan_json"])
        catalog = svc._catalog(row["catalog_version"])
        market = svc._data(row["data_path"])
        db.execute("UPDATE stages SET phase='RUNNING' WHERE session_id=?", (sid,))
    diagnosis = ScriptedResearcher().propose(staged["model_context"])
    final = svc.cycle.advance(sid, catalog, market, _SubmittedProvider(plan, diagnosis))
    return svc, final


def test_crashed_gateway_reconcile_restores_s7_and_stable_retry(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    sid = started["session_id"]
    researcher = ScriptedResearcher()
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": sid, "checkpoint_token": started["checkpoint_token"],
        "plan": researcher.propose(started["model_context"]),
    })
    svc, final = _simulate_gateway_crash_after_cycle_commit(tmp_path, server, staged)
    assert final["completed_generations"] == 1
    with svc._connect() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM experiment_reports WHERE session_id=?", (sid,)
        ).fetchone()[0] == 0

    restarted = create_mcp_server(
        project_root=tmp_path / "project", state_dir=tmp_path / "state",
    )
    result = restarted._dispatch("reconcile_algorithm_research", {"session_id": sid})
    assert result["checkpoint_phase"] == "AWAITING_PLAN"
    assert result["completed_generations"] == 1
    assert result["history"] == final["history"]
    assert result["latest_controlled_experiments"]["generation"] == 1
    assert result["model_context"]["prior_research"]["controlled_experiments"][
        "record_hash"
    ] == result["latest_controlled_experiments"]["record_hash"]
    again = restarted._dispatch("reconcile_algorithm_research", {"session_id": sid})
    assert result == again
    with svc._connect() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM experiment_reports WHERE session_id=?", (sid,)
        ).fetchone()[0] == 1
    assert result["orders_enabled"] is False


def test_reconcile_after_final_generation_preserves_final_evidence(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    model = ScriptedResearcher()
    sid = started["session_id"]
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": sid, "checkpoint_token": started["checkpoint_token"],
        "plan": model.propose(started["model_context"]),
    })
    gen1 = server._dispatch("submit_algorithm_diagnosis", {
        "session_id": sid, "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": model.propose(staged["model_context"]),
    })
    staged2 = server._dispatch("submit_algorithm_plan", {
        "session_id": sid, "checkpoint_token": gen1["checkpoint_token"],
        "plan": model.propose(gen1["model_context"]),
    })
    _, final = _simulate_gateway_crash_after_cycle_commit(tmp_path, server, staged2)
    assert final["status"] == "COMPLETED"
    recovered = server._dispatch("reconcile_algorithm_research", {"session_id": sid})
    assert recovered["status"] == "COMPLETED"
    assert recovered["history"] == final["history"]
    assert recovered["latest_controlled_experiments"]["generation"] == 2
    assert recovered == server._dispatch("reconcile_algorithm_research", {"session_id": sid})


def test_interrupted_executing_claim_reconcile_then_resume_are_idempotent(
    tmp_path: Path,
) -> None:
    server, started = _setup(tmp_path)
    svc = _service(tmp_path)
    sid = started["session_id"]
    with svc._connect() as db:
        db.execute("UPDATE stages SET phase='RUNNING' WHERE session_id=?", (sid,))
    with svc.cycle._connect() as db:
        db.execute(
            "UPDATE sessions SET status='EXECUTING',running_token=? WHERE id=?",
            ("simulated_stale_worker", sid),
        )
    recovered = server._dispatch("reconcile_algorithm_research", {"session_id": sid})
    assert recovered["status"] == "INTERRUPTED"
    assert recovered["checkpoint_phase"] == "INTERRUPTED"
    assert recovered["completed_generations"] == 0
    assert recovered == server._dispatch("reconcile_algorithm_research", {"session_id": sid})

    with svc._connect() as db:
        interrupted_token = db.execute(
            "SELECT token FROM stages WHERE session_id=?", (sid,)
        ).fetchone()[0]
    resumed = server._dispatch("resume_algorithm_research", {"session_id": sid})
    assert resumed["status"] == "AWAITING_PROVIDER"
    assert resumed["checkpoint_phase"] == "AWAITING_PLAN"
    assert resumed["checkpoint_token"] != interrupted_token
    assert resumed == server._dispatch("resume_algorithm_research", {"session_id": sid})
    with pytest.raises(ValueError, match="reconcile|RUNNING|stalled"):
        server._dispatch("reconcile_algorithm_research", {"session_id": sid})


def test_recovery_receipt_tamper_is_rejected(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    svc = _service(tmp_path)
    sid = started["session_id"]
    with svc._connect() as db:
        db.execute("UPDATE stages SET phase='RUNNING' WHERE session_id=?", (sid,))
    server._dispatch("reconcile_algorithm_research", {"session_id": sid})
    with svc._connect() as db:
        db.execute(
            "UPDATE recovery_receipts SET receipt_hash=? WHERE session_id=?",
            ("0" * 64, sid),
        )
    with pytest.raises(ValueError, match="integrity|tamper"):
        server._dispatch("reconcile_algorithm_research", {"session_id": sid})


def test_reconcile_invalid_evidence_keeps_checkpoint_unrecovered(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    sid = started["session_id"]
    researcher = ScriptedResearcher()
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": sid, "checkpoint_token": started["checkpoint_token"],
        "plan": researcher.propose(started["model_context"]),
    })
    svc, _ = _simulate_gateway_crash_after_cycle_commit(tmp_path, server, staged)
    # A stored controlled experiment from another process was corrupted.
    svc.evaluate_experiments({"session_id": sid, "generation": 1})
    with svc._connect() as db:
        db.execute("UPDATE experiment_reports SET report_hash=? WHERE session_id=?",
                   ("0" * 64, sid))
    with pytest.raises(ValueError, match="integrity"):
        server._dispatch("reconcile_algorithm_research", {"session_id": sid})
    with svc._connect() as db:
        assert db.execute("SELECT phase FROM stages WHERE session_id=?",
                          (sid,)).fetchone()[0] == "RUNNING"
