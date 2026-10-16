"""P0-3B parent selection must fail closed before any counted promotion."""

from copy import deepcopy

import pytest

from core.integrity.hashes import content_hash
from research.llm.lineage_selection import (
    LineageSelectionError,
    choose_development_parent,
)


def _candidate(**overrides):
    value = {
        "source_generation": 29,
        "source_evidence_hash": "a" * 64,
        "lineage_report_hash": "b" * 64,
        "successor_strategy_hash": "c" * 64,
        "child_total_return": 0.44,
        "successor_total_return": 0.49,
        "child_max_drawdown": 0.21,
        "successor_max_drawdown": 0.16,
        "successor_closed_trades": 48,
        "successor_market_exposure": 0.32,
        "qqq_buy_and_hold_return": 1.87,
        "qqq_exposure_matched_return": 0.59,
        "strategy_equity_hash": "d" * 64,
        "replay_verified": True,
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    value.update(overrides)
    return value


def test_selection_records_all_tradeoffs_and_qqq_but_does_not_claim_profitability():
    result = choose_development_parent([_candidate()])
    assert result is not None
    assert result["successor_strategy_hash"] == "c" * 64
    assert result["parent_quality"]["max_drawdown"] == pytest.approx(0.16)
    assert result["parent_quality"]["closed_trades"] == 48
    assert result["parent_quality"]["market_exposure"] == pytest.approx(0.32)
    assert result["parent_quality"]["qqq_buy_and_hold_return"] == pytest.approx(1.87)
    assert result["parent_quality"]["qqq_exposure_matched_return"] == pytest.approx(0.59)
    assert result["relative_qqq_bh_pp"] == pytest.approx(-138.0)
    assert result["status"] == "PARENT_SELECTED_NOT_COUNTED"
    assert result["independent_oos_approved"] is False


@pytest.mark.parametrize("changed", [
    {"successor_closed_trades": 29},
    {"successor_market_exposure": 0.0},
    {"successor_market_exposure": 1.01},
    {"successor_total_return": 0.41},
    {"successor_max_drawdown": 0.27},
    {"replay_verified": False},
    {"broker_executable": True},
    {"independent_oos_approved": True},
])
def test_ineligible_or_non_replayed_candidates_cannot_be_selected(changed):
    assert choose_development_parent([_candidate(**changed)]) is None


def test_conflicting_hash_or_nonfinite_metric_fails_closed():
    with pytest.raises(LineageSelectionError):
        choose_development_parent([_candidate(lineage_report_hash="broken")])
    with pytest.raises(LineageSelectionError):
        choose_development_parent([_candidate(successor_total_return=float("nan"))])


def test_deterministic_selection_is_independent_of_arrival_order_and_retry():
    good = _candidate()
    better = _candidate(
        source_generation=30,
        lineage_report_hash="e" * 64,
        source_evidence_hash="f" * 64,
        successor_strategy_hash="0" * 64,
        successor_total_return=0.53,
        successor_max_drawdown=0.14,
        successor_closed_trades=49,
    )
    first = choose_development_parent([good, better])
    assert first == choose_development_parent([better, deepcopy(good)])
    assert first is not None and first["source_generation"] == 30


def test_live_lineage_candidate_replay_uses_actual_fills_and_qqq_development_benchmark():
    # Read-only fixture. Never mutate the 133/300 production session.
    from research.llm.lineage_selection import replay_lineage_candidate
    from tests.research.test_lineage_p0_3 import _actual_source
    catalog, market, original, report, proposal, continuation = _actual_source()
    from research.llm.lineage_replay import verified_child_successor
    lineage = verified_child_successor(
        catalog, market, original, report,
        hypothesis_id=proposal["hypothesis_id"],
        expected_child_strategy_hash=proposal["proposal_child_hash"],
        continuation_intent=continuation,
    )
    candidate = replay_lineage_candidate(catalog, market, original, report, lineage)
    assert candidate["replay_verified"] is True
    assert candidate["successor_strategy_hash"] == lineage["successor_strategy_hash"]
    assert candidate["successor_closed_trades"] == 48
    assert 0 < candidate["successor_market_exposure"] < 1
    assert candidate["qqq_buy_and_hold_return"] > 1
    assert choose_development_parent([candidate]) is not None


def test_gateway_freezes_parent_for_next_counted_generation_and_retries(tmp_path, monkeypatch):
    import json

    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    from tests.integrations.test_academic_mcp_sessions import _setup
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    server, started = _setup(tmp_path)
    scripted = ScriptedResearcher()
    sid = started["session_id"]
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": sid,
        "checkpoint_token": started["checkpoint_token"],
        "plan": scripted.propose(started["model_context"]),
    })
    completed = server._dispatch("submit_algorithm_diagnosis", {
        "session_id": sid,
        "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": scripted.propose(staged["model_context"]),
    })
    original = completed["history"][0]
    sid = completed["session_id"]
    fake_body = {
        "schema": "p0-3-child-to-successor-development-v1",
        "source_generation": 1,
        "source_evidence_hash": original["evidence_hash"],
        "hypothesis_id": original["hypothesis_ids"][0],
        "reproduced_child_strategy_hash": "7" * 64,
        "successor_strategy_hash": "c" * 64,
        "successor_final_equity": 14900.0,
        "successor_total_return": 0.49,
        "successor_max_drawdown": 0.16,
        "improvement_vs_child_pp": 5.0,
        "continuation_intent": original["experiments"][0]["proposed_intent"],
    }
    fake = {**fake_body, "report_hash": content_hash(fake_body)}
    service = AcademicMCPCheckpointService(
        project_root=tmp_path / "project", state_dir=tmp_path / "state"
    )
    with service._connect() as db:
        db.execute(
            "INSERT INTO successor_lineages VALUES(?,?,?,?,?)",
            (sid, 1, "8" * 64, json.dumps(fake), fake["report_hash"]),
        )
    expected = _candidate(
        source_generation=1,
        source_evidence_hash=original["evidence_hash"],
        lineage_report_hash=fake["report_hash"],
    )
    import application.academic_checkpoint_service as gateway
    monkeypatch.setattr(gateway, "replay_lineage_candidate",
                        lambda *args: expected)
    selected = service.get({"session_id": sid})["model_context"][
        "selected_development_parent"
    ]
    assert selected["source_generation"] == 1
    assert selected["status"] == "PARENT_SELECTED_NOT_COUNTED"
    assert service.get({"session_id": sid})["model_context"][
        "selected_development_parent"
    ] == selected
    monkeypatch.setattr(gateway, "replay_lineage_candidate",
                        lambda *args: pytest.fail("selection was not frozen"))
    assert service.get({"session_id": sid})["model_context"][
        "selected_development_parent"
    ] == selected
    assert service.get({"session_id": sid})["completed_generations"] == 1
    with service._connect() as db:
        db.execute(
            "UPDATE parent_selections SET selection_hash=? WHERE session_id=?",
            ("f" * 64, sid),
        )
    with pytest.raises(ValueError, match="selection|integrity"):
        service.get({"session_id": sid})
