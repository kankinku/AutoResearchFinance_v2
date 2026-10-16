"""T4 regression: rejected duplicate plans must NOT interrupt the MCP research session."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _commit_first(server: object, started: dict) -> tuple[dict, dict]:
    model = ScriptedResearcher()
    sid = started["session_id"]
    first_plan = model.propose(started["model_context"])
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": sid,
        "checkpoint_token": started["checkpoint_token"],
        "plan": first_plan,
    })
    first = server._dispatch("submit_algorithm_diagnosis", {
        "session_id": sid,
        "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": model.propose(staged["model_context"]),
    })
    assert first["completed_generations"] == 1
    assert first["checkpoint_phase"] == "AWAITING_PLAN"
    return first_plan, first


def test_semantic_duplicate_rejected_before_staging_and_session_stays_ready(
    tmp_path: Path,
) -> None:
    server, started = _setup(tmp_path)
    first_plan, previous = _commit_first(server, started)
    sid, token = previous["session_id"], previous["checkpoint_token"]
    prior_history = deepcopy(previous["history"])
    dupe = deepcopy(first_plan)
    dupe["plan_id"] = "different_name_same_algorithm"
    with pytest.raises(ValueError, match="DUPLICATE_SEMANTIC_PLAN"):
        server._dispatch("submit_algorithm_plan", {
            "session_id": sid, "checkpoint_token": token, "plan": dupe,
        })
    unchanged = server._dispatch("get_algorithm_research", {"session_id": sid})
    assert unchanged["checkpoint_phase"] == "AWAITING_PLAN"
    assert unchanged["status"] == "AWAITING_PROVIDER"
    assert unchanged["checkpoint_token"] == token
    assert unchanged["history"] == prior_history
    assert unchanged["error_type"] is None
    assert not unchanged["orders_enabled"]


def test_distinct_structure_same_effective_signals_rejected_without_interrupt(
    tmp_path: Path,
) -> None:
    server, started = _setup(tmp_path)
    first_plan, previous = _commit_first(server, started)
    sid, token = previous["session_id"], previous["checkpoint_token"]
    duplicate_signals = deepcopy(first_plan)
    duplicate_signals["plan_id"] = "different_threshold_same_signals"
    duplicate_signals["cases"][0]["min_score"] = 0.55
    with pytest.raises(ValueError, match="DUPLICATE_EFFECTIVE_SIGNALS"):
        server._dispatch("submit_algorithm_plan", {
            "session_id": sid, "checkpoint_token": token,
            "plan": duplicate_signals,
        })
    state = server._dispatch("get_algorithm_research", {"session_id": sid})
    assert state["checkpoint_phase"] == "AWAITING_PLAN"
    assert state["status"] == "AWAITING_PROVIDER"
    assert state["checkpoint_token"] == token
    assert state["completed_generations"] == 1
    assert state["history"] == previous["history"]
    assert state["error_type"] is None

    # The model can submit a genuinely distinct plan with that SAME token
    # without resuming or rewriting the previous generation.
    model = ScriptedResearcher()
    novel = model.propose(state["model_context"])
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": sid, "checkpoint_token": token, "plan": novel,
    })
    assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    final = server._dispatch("submit_algorithm_diagnosis", {
        "session_id": sid, "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": model.propose(staged["model_context"]),
    })
    assert final["completed_generations"] == 2
    assert final["status"] == "COMPLETED"
    assert final["orders_enabled"] is False
    assert final["history"][0]["evidence_hash"] == previous["history"][0]["evidence_hash"]
    assert final["latest_controlled_experiments"]["generation"] == 2
