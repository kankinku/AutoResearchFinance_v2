"""Optional S2 protection: same actual fill schedule does not consume a cycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.research.test_p0_3b_reinherit import SID, _intent, _isolated_service


def test_optional_same_execution_refused_without_advancing_checkpoint(tmp_path: Path) -> None:
    svc = _isolated_service(tmp_path)
    before = svc.get({"session_id": SID})
    with svc._connect() as db:
        _, catalog, data, state = svc._state(db, SID)
    parent, _, _ = svc._selected_ir(catalog, data, state)
    original = float(parent.strategy.exit.conditions[0].value)
    near_value = original + 1e-12
    plan = _intent(parent.strategy.strategy_id, near_value)
    with pytest.raises(ValueError, match="UNCHANGED_INHERITED_EXECUTIONS"):
        svc.submit_plan(
            {
                "session_id": SID,
                "checkpoint_token": before["checkpoint_token"],
                "plan": plan,
                "require_execution_change": True,
            }
        )
    after = svc.get({"session_id": SID})
    assert after["completed_generations"] == before["completed_generations"]
    assert after["checkpoint_token"] == before["checkpoint_token"]
    assert after["checkpoint_phase"] == "AWAITING_PLAN"
    assert [x["evidence_hash"] for x in after["history"]] == [
        x["evidence_hash"] for x in before["history"]
    ]


def test_execution_guard_rejects_invalid_flag_without_claiming_checkpoint(tmp_path: Path) -> None:
    svc = _isolated_service(tmp_path)
    before = svc.get({"session_id": SID})
    with pytest.raises(ValueError, match="boolean"):
        svc.submit_plan(
            {
                "session_id": SID,
                "checkpoint_token": before["checkpoint_token"],
                "plan": {},
                "require_execution_change": "true",
            }
        )
    assert svc.get({"session_id": SID})["checkpoint_token"] == before["checkpoint_token"]
