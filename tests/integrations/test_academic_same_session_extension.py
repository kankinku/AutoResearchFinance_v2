"""Operator-only same-session continuation across a completed academic checkpoint."""

from pathlib import Path

import pytest

from application.academic_checkpoint_service import (
    AcademicMCPCheckpointService,
)
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _finish_two(tmp_path: Path):
    server, started = _setup(tmp_path)
    sid = started["session_id"]
    scripted = ScriptedResearcher()
    current = started
    for _ in range(2):
        p = server._dispatch(
            "submit_algorithm_plan",
            {
                "session_id": sid,
                "checkpoint_token": current["checkpoint_token"],
                "plan": scripted.propose(current["model_context"]),
            },
        )
        current = server._dispatch(
            "submit_algorithm_diagnosis",
            {
                "session_id": sid,
                "checkpoint_token": p["checkpoint_token"],
                "diagnosis": scripted.propose(p["model_context"]),
            },
        )
    assert current["checkpoint_phase"] == "COMPLETED"
    assert current["final_report"]["all_proposed_hypotheses_measured"] is True
    return server, current, scripted


def test_completed_checkpoint_can_extend_same_id_without_touching_evidence(tmp_path: Path):
    server, old, scripted = _finish_two(tmp_path)
    sid = old["session_id"]
    service = AcademicMCPCheckpointService(
        project_root=tmp_path / "project",
        state_dir=tmp_path / "state",
    )
    head = old["history"][-1]["evidence_hash"]
    fresh = service.extend_completed_session(sid, additional_generations=100)
    assert fresh["session_id"] == sid
    assert (fresh["requested_generations"], fresh["completed_generations"]) == (102, 2)
    assert fresh["checkpoint_phase"] == "AWAITING_PLAN"
    assert fresh["checkpoint_token"] != old.get("checkpoint_token")
    assert [x["evidence_hash"] for x in fresh["history"]] == [
        x["evidence_hash"] for x in old["history"]
    ]
    assert fresh["history"][-1]["evidence_hash"] == head
    assert fresh["final_report"] is None
    assert (
        service.evaluate_experiments({"session_id": sid, "generation": 2})[
            "original_generation_evidence_hash"
        ]
        == head
    )
    with service._connect() as db:
        proof = db.execute(
            "SELECT old_requested,new_requested,completed,evidence_head "
            "FROM session_extensions WHERE session_id=?",
            (sid,),
        ).fetchone()
        assert tuple(proof) == (2, 102, 2, head)
    p = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": sid,
            "checkpoint_token": fresh["checkpoint_token"],
            "plan": scripted.propose(fresh["model_context"]),
        },
    )
    final = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": sid,
            "checkpoint_token": p["checkpoint_token"],
            "diagnosis": scripted.propose(p["model_context"]),
        },
    )
    assert final["completed_generations"] == 3
    assert final["requested_generations"] == 102
    assert final["history"][1]["evidence_hash"] == head
    assert final["history"][2]["previous_evidence_hash"] == head
    assert final["checkpoint_phase"] == "AWAITING_PLAN"
    assert final["orders_enabled"] is False
    assert final["independent_oos_approved"] is False


def test_extension_fails_closed_on_wrong_stage_and_size(tmp_path: Path):
    server, old, _ = _finish_two(tmp_path)
    sid = old["session_id"]
    svc = AcademicMCPCheckpointService(
        project_root=tmp_path / "project",
        state_dir=tmp_path / "state",
    )
    with pytest.raises(ValueError, match="operator extension"):
        svc.extend_completed_session(sid, additional_generations=101)
    with pytest.raises(ValueError, match="operator extension"):
        svc.extend_completed_session(sid, additional_generations=True)
    with svc._connect() as db:
        db.execute(
            "UPDATE stages SET plan_json='stale' WHERE session_id=?",
            (sid,),
        )
    with pytest.raises(ValueError, match="concurrent|inconsistent"):
        svc.extend_completed_session(sid, additional_generations=100)
    from research.llm.autonomous_cycle import AcademicCycleService

    with AcademicCycleService(svc.cycle.db_path)._connect() as db:
        row = db.execute(
            "SELECT requested,completed,status FROM sessions WHERE id=?",
            (sid,),
        ).fetchone()
        assert tuple(row) == (2, 2, "COMPLETED")


def test_mcp_s7_allows_later_generation_without_enlarging_start():
    schema = {x["name"]: x for x in chatgpt_tools()}
    assert (
        schema["evaluate_algorithm_experiments"]["inputSchema"]["properties"]["generation"][
            "maximum"
        ]
        == 200
    )
    assert (
        schema["start_algorithm_research"]["inputSchema"]["properties"]["generations"]["maximum"]
        == 100
    )
