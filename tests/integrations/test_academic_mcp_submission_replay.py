"""Retrying an acknowledged MCP submission must never advance a generation twice."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from integrations.codex_mcp_core import create_mcp_server
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def test_plan_retry_after_lost_reply_preserves_checkpoint(tmp_path: Path) -> None:
    server, initial = _setup(tmp_path)
    model = ScriptedResearcher()
    sid = initial["session_id"]
    plan = model.propose(initial["model_context"])
    request = {
        "session_id": sid, "checkpoint_token": initial["checkpoint_token"], "plan": plan,
    }
    staged = server._dispatch("submit_algorithm_plan", request)
    # The caller lost the response, restarted and sent the exact same request.
    restarted = create_mcp_server(
        project_root=tmp_path / "project", state_dir=tmp_path / "state",
    )
    assert restarted._dispatch("submit_algorithm_plan", request) == staged
    assert restarted._dispatch("get_algorithm_research", {"session_id": sid})[
        "completed_generations"
    ] == 0
    mutated = deepcopy(request)
    mutated["plan"]["plan_id"] = "different_plan"
    with pytest.raises(ValueError, match="conflict|stale|checkpoint|state"):
        restarted._dispatch("submit_algorithm_plan", mutated)
    diagnosis = model.propose(staged["model_context"])
    result = restarted._dispatch("submit_algorithm_diagnosis", {
        "session_id": sid, "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": diagnosis,
    })
    assert result["completed_generations"] == 1
    with pytest.raises(ValueError, match="stale|checkpoint|state|plan"):
        restarted._dispatch("submit_algorithm_plan", request)


def test_diagnosis_retry_preserves_experiment_and_next_token(tmp_path: Path) -> None:
    server, initial = _setup(tmp_path)
    model = ScriptedResearcher()
    sid = initial["session_id"]
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": sid, "checkpoint_token": initial["checkpoint_token"],
        "plan": model.propose(initial["model_context"]),
    })
    request = {
        "session_id": sid, "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": model.propose(staged["model_context"]),
    }
    completed = server._dispatch("submit_algorithm_diagnosis", request)
    assert completed["completed_generations"] == 1
    restarted = create_mcp_server(
        project_root=tmp_path / "project", state_dir=tmp_path / "state",
    )
    assert restarted._dispatch("submit_algorithm_diagnosis", request) == completed
    assert completed["latest_controlled_experiments"]["generation"] == 1
    bad = deepcopy(request)
    bad["diagnosis"]["summary"] += " Changed response."
    with pytest.raises(ValueError, match="conflict|stale|checkpoint|state"):
        restarted._dispatch("submit_algorithm_diagnosis", bad)
    with pytest.raises(ValueError, match="conflict|stale|checkpoint|state"):
        restarted._dispatch("submit_algorithm_diagnosis", {
            **request, "require_signal_change": True,
        })
    # Moving to the next generation invalidates the previous retry receipt.
    restarted._dispatch("submit_algorithm_plan", {
        "session_id": sid, "checkpoint_token": completed["checkpoint_token"],
        "plan": model.propose(completed["model_context"]),
    })
    with pytest.raises(ValueError, match="stale|checkpoint|state"):
        restarted._dispatch("submit_algorithm_diagnosis", request)


def test_modified_receipt_is_not_trusted(tmp_path: Path) -> None:
    server, initial = _setup(tmp_path)
    request = {
        "session_id": initial["session_id"],
        "checkpoint_token": initial["checkpoint_token"],
        "plan": ScriptedResearcher().propose(initial["model_context"]),
    }
    server._dispatch("submit_algorithm_plan", request)
    service = AcademicMCPCheckpointService(
        project_root=tmp_path / "project", state_dir=tmp_path / "state",
    )
    with service._connect() as db:
        db.execute(
            "UPDATE submission_receipts SET request_hash=? WHERE session_id=?",
            ("0" * 64, initial["session_id"]),
        )
    with pytest.raises(ValueError, match="integrity|tamper"):
        server._dispatch("submit_algorithm_plan", request)
