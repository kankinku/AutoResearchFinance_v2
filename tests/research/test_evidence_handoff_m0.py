"""Canonical read-only evidence handoff: integration with actual Quant journal."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from application.research_handoff_builder import (
    ResearchHandoffError,
    build_research_handoff,
)
from core.integrity.hashes import content_hash
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _history_fixture(tmp_path: Path, generations: int = 2):
    server, state = _setup(tmp_path)
    model = ScriptedResearcher()
    receipts = {}
    for n in range(1, generations + 1):
        staged = server._dispatch(
            "submit_algorithm_plan",
            {
                "session_id": state["session_id"],
                "checkpoint_token": state["checkpoint_token"],
                "plan": model.propose(state["model_context"]),
            },
        )
        state = server._dispatch(
            "submit_algorithm_diagnosis",
            {
                "session_id": state["session_id"],
                "checkpoint_token": staged["checkpoint_token"],
                "diagnosis": model.propose(staged["model_context"]),
            },
        )
        receipts[n] = state["latest_controlled_experiments"]
    return server, state, receipts


def test_repeated_build_from_actual_quant_proofs_is_deterministic(tmp_path: Path):
    _, state, receipts = _history_fixture(tmp_path)
    before = deepcopy(state)
    result = build_research_handoff(state, receipts, max_chars=20000)
    assert state == before
    assert result == build_research_handoff(state, receipts, max_chars=20000)
    assert result["completed_generations"] == 2
    assert len(result["events"]) == 2
    assert all(
        e["evidence_hash"] == state["history"][i]["evidence_hash"]
        for i, e in enumerate(result["events"])
    )
    assert all(
        e["s7_record_hash"] == receipts[i]["record_hash"]
        for i, e in ((1, result["events"][0]), (2, result["events"][1]))
    )
    assert all(e["claims_causal_verified"] is False for e in result["events"])
    assert result["handoff_hash"] == content_hash(
        {k: v for k, v in result.items() if k != "handoff_hash"}
    )
    assert result["orders_enabled"] is False
    assert result["independent_oos_approved"] is False
    assert "checkpoint_token" not in str(result)
    assert result["decision_mode"] == "NO_AUTOMATIC_STRATEGY_SELECTION"


def test_corrupt_history_or_s7_refused(tmp_path: Path):
    _, state, receipts = _history_fixture(tmp_path)
    changed = deepcopy(state)
    changed["history"][0]["analysis_summary"] = "tampers with canonical evidence"
    with pytest.raises(ResearchHandoffError, match="canonical"):
        build_research_handoff(changed, receipts)
    changed = deepcopy(receipts)
    changed[1]["report"]["experiments"][0]["status"] = "FORGED_RESULT"
    with pytest.raises(ResearchHandoffError, match="S7"):
        build_research_handoff(state, changed)
    with pytest.raises(ResearchHandoffError, match="missing"):
        build_research_handoff(state, {1: receipts[1]})


def test_stale_handoff_and_changed_checkpoint_rejected(tmp_path: Path):
    server, state, receipts = _history_fixture(tmp_path, generations=1)
    out = build_research_handoff(state, receipts)
    state2 = server._dispatch("get_algorithm_research", {"session_id": state["session_id"]})
    from application.research_handoff_builder import assert_handoff_fresh

    assert_handoff_fresh(out, state2)
    forged = deepcopy(out)
    forged["completed_generations"] = 0
    with pytest.raises(ResearchHandoffError, match="handoff"):
        assert_handoff_fresh(forged, state2)
    changed = deepcopy(state2)
    changed["dataset_hash"] = "a" * 64
    with pytest.raises(ResearchHandoffError, match="stale|canonical"):
        assert_handoff_fresh(out, changed)


def test_overbudget_requires_full_evidence_not_truncation(tmp_path: Path):
    _, state, receipts = _history_fixture(tmp_path)
    result = build_research_handoff(state, receipts, max_chars=1000)
    assert result["delivery_status"] == "ESCALATE_EVIDENCE_REPLAY"
    assert len(result["events"]) == 2
    assert all(e["s7_record_hash"] for e in result["events"])
    assert result["truncated"] is False


def test_no_host_and_unproven_model_are_not_claimed(tmp_path: Path):
    _, state, receipts = _history_fixture(tmp_path)
    result = build_research_handoff(state, receipts)
    assert result["genuine_provider_verified_generations"] == 0
    assert result["client_can_autonomously_start_chatgpt_turn"] is False
    assert result["data_scope"] == "NON_PIT_DEVELOPMENT_ONLY"


def test_compact_read_view_refs_are_evidence_bound_without_raw_history(tmp_path: Path):
    from application.research_handoff_builder import compact_handoff_view

    _, state, receipts = _history_fixture(tmp_path)
    handoff = build_research_handoff(state, receipts, max_chars=20000)
    view = compact_handoff_view(handoff, state, receipts)
    assert view["schema"] == "quant-research-compact-view-m0-v1"
    assert view["handoff_hash"] == handoff["handoff_hash"]
    assert "events" not in view and "checkpoint_token" not in str(view)
    assert view["brief"]["last_three_events"]
    assert view["new_verified_provider_generations"] == 0
    assert view["orders_enabled"] is False
    assert view["independent_oos_approved"] is False
    assert len(str(view)) < len(str(handoff))
    forged = deepcopy(receipts)
    forged[2]["report"]["experiments"][0]["status"] = "TAMPER"
    with pytest.raises(ResearchHandoffError):
        compact_handoff_view(handoff, state, forged)


def test_overbudget_fails_compact_view_instead_of_dropping_evidence(tmp_path: Path):
    from application.research_handoff_builder import compact_handoff_view

    _, state, receipts = _history_fixture(tmp_path)
    handoff = build_research_handoff(state, receipts, max_chars=1000)
    with pytest.raises(ResearchHandoffError, match="replay"):
        compact_handoff_view(handoff, state, receipts)
