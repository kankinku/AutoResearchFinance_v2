"""P0 paired development economics are not broker approval or causal learning."""

from __future__ import annotations

import pytest

from core.integrity.hashes import content_hash
from research.llm.economic_feedback import (
    EconomicFeedbackError,
    build_economic_feedback,
    gate_research_direction,
)


def example(
    *,
    parent_equity: float = 12000.0,
    child_equity: float = 13000.0,
    child_fills: int = 44,
    trade_metric: str = "trade_count",
    status: str = "DIRECTION_MATCHED_DEVELOPMENT_ONLY",
):
    hypothesis = {
        "hypothesis_id": "test_one",
        "proposal_child_hash": "c" * 64,
        "proposed_intent": {
            "mode": "structure",
            "parent_ids": ["parent1"],
            "operations": [
                {
                    "op": "ADD_RULE",
                    "path": "entry.conditions",
                    "condition": {"left": "ema_direction_20", "op": "greater_than", "value": 0.5},
                }
            ],
            "rationale": "Evaluate a narrower entry filter.",
        },
    }
    history = [
        {
            "generation": 1,
            "evidence_hash": "a" * 64,
            "diagnostic_proposal_hash": "d" * 64,
            "metrics": {"total_return": 0.2, "max_drawdown": 0.12, "trade_count": 29},
            "measured_final_equity": 12000.0,
            "experiments": [hypothesis],
        }
    ]
    trial = {
        "hypothesis_id": "test_one",
        "child_strategy_hash": "c" * 64,
        "parent_final_equity": parent_equity,
        "child_final_equity": child_equity,
        "parent_fill_count": 58,
        "child_fill_count": child_fills,
        "metric": trade_metric,
        "status": status,
        "causal_status": "NOT_ESTABLISHED",
        "execution_delta": {
            "added_event_count": 2,
            "removed_event_count": 16,
            "resized_event_count": 6,
        },
        "development_windows": [
            {
                "parent_max_drawdown": 0.05,
                "child_max_drawdown": 0.04,
                "parent_total_return": 0.07,
                "child_total_return": 0.09,
            }
        ]
        * 4,
    }
    body = {
        "generation": 1,
        "original_generation_evidence_hash": "a" * 64,
        "study_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        "report": {
            "causal_status": "NOT_ESTABLISHED",
            "out_of_sample_approved": False,
            "broker_executable": False,
            "diagnostic_proposal_hash": "d" * 64,
            "experiments": [trial],
        },
    }
    return history, {1: {**body, "record_hash": content_hash(body)}}


def test_no_experiments_does_not_pretend_to_have_learned_alpha():
    r = build_economic_feedback([], {})
    assert r["tested_experiments"] == 0
    assert r["research_objective"]["primary_metric"] == "total_return"
    assert "trade_count" not in r["research_objective"]["primary_metrics"]
    assert r["automatic_child_promotion"] is False
    assert r["independent_oos_approved"] is False


def test_worse_return_not_counted_as_economic_success_even_if_direction_matches():
    h, r = example(child_equity=10500.0)
    e = build_economic_feedback(h, r)
    assert e["outcomes"]["return_worse"] == 1
    assert e["outcomes"]["return_better"] == 0
    assert e["latest"]["return_delta_pp"] == pytest.approx(-15.0)
    assert e["latest"]["economic_direction"] == "RETURN_WORSE_DEVELOPMENT"
    direction = {
        "recommended_mode": "EVOLVE",
        "reason_code": "LAST_CONTROL_MEASURED_NONTRIVIAL_SIGNAL_CHANGE",
        "completed_generations": 1,
    }
    revised = gate_research_direction(direction, e)
    assert revised["recommended_mode"] == "TEST_HYPOTHESIS"
    assert revised["reason_code"] == "LATEST_MATCHED_CONTROL_LOWER_DEVELOPMENT_RETURN"
    assert direction["recommended_mode"] == "EVOLVE"


def test_profitable_child_is_review_only_and_contains_replayable_provenance():
    h, r = example(child_equity=13200.0, child_fills=64)
    out = build_economic_feedback(h, r)
    assert out["outcomes"]["return_better"] == 1
    assert out["latest"]["return_delta_pp"] == pytest.approx(12.0)
    assert out["review_candidates"][0]["hypothesis_id"] == "test_one"
    assert (
        out["review_candidates"][0]["proposed_intent"]["operations"][0]["condition"]["left"]
        == "ema_direction_20"
    )
    assert out["review_candidates"][0]["child_closed_trades_estimate"] == 32
    assert out["review_candidates"][0]["causal_status"] == "NOT_ESTABLISHED"
    assert out["automatic_child_promotion"] is False
    assert (
        gate_research_direction({"recommended_mode": "EVOLVE", "completed_generations": 1}, out)[
            "recommended_mode"
        ]
        == "EVOLVE"
    )


def test_low_activity_is_not_a_successful_promotable_candidate():
    h, r = example(child_equity=15000.0, child_fills=0)
    out = build_economic_feedback(h, r)
    assert out["outcomes"]["return_better"] == 1
    assert out["review_candidates"] == []
    revised = gate_research_direction(
        {"recommended_mode": "EVOLVE", "completed_generations": 1}, out
    )
    assert revised["recommended_mode"] == "EXPLORE"
    assert revised["reason_code"] == "LATEST_CONTROL_INACTIVE_CHILD"


def test_tampered_or_inconsistent_report_fails_closed():
    h, r = example()
    r[1]["report"]["experiments"][0]["child_final_equity"] = 99999
    with pytest.raises(EconomicFeedbackError, match="integrity"):
        build_economic_feedback(h, r)
    h, r = example(parent_equity=12001)
    with pytest.raises(EconomicFeedbackError, match="parent equity"):
        build_economic_feedback(h, r)
    h, r = example()
    r[1]["report"]["experiments"][0]["child_strategy_hash"] = "f" * 64
    body = {k: v for k, v in r[1].items() if k != "record_hash"}
    r[1]["record_hash"] = content_hash(body)
    with pytest.raises(EconomicFeedbackError, match="child strategy"):
        build_economic_feedback(h, r)


def test_economics_direction_not_overridden_when_no_matching_generation():
    _, report = example()
    e = build_economic_feedback([], {})
    before = {"recommended_mode": "EVOLVE", "completed_generations": 4}
    assert gate_research_direction(before, e) == before
    assert len(report) == 1


def test_live_mcp_checkpoint_exposes_economic_feedback_without_changing_cycle(tmp_path):
    from tests.integrations.test_academic_mcp_sessions import _setup
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    server, started = _setup(tmp_path)
    assert started["model_context"]["economic_feedback"]["tested_experiments"] == 0
    before_token = started["checkpoint_token"]
    scripted = ScriptedResearcher()
    plan = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": before_token,
            "plan": scripted.propose(started["model_context"]),
        },
    )
    result = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": plan["checkpoint_token"],
            "diagnosis": scripted.propose(plan["model_context"]),
        },
    )
    econ = result["model_context"]["economic_feedback"]
    assert econ["tested_experiments"] == 1
    assert sum(econ["outcomes"].values()) == 1
    assert econ["research_objective"]["trade_count_is_not_success"] is True
    assert econ["independent_oos_approved"] is False
    assert econ["automatic_child_promotion"] is False
    assert result["orders_enabled"] is False
    assert result["checkpoint_phase"] == "AWAITING_PLAN"
    assert result["completed_generations"] == 1
    assert (
        server._dispatch(
            "get_algorithm_research",
            {
                "session_id": started["session_id"],
            },
        )["model_context"]["economic_feedback"]
        == econ
    )


def test_small_activity_gain_cannot_automatically_trigger_evolve():
    history, reports = example(child_equity=18000.0, child_fills=20)
    evidence = build_economic_feedback(history, reports)
    assert evidence["review_candidates"] == []
    direction = {"recommended_mode": "EVOLVE", "completed_generations": 1}
    result = gate_research_direction(direction, evidence)
    assert result["recommended_mode"] == "TEST_HYPOTHESIS"
    assert result["reason_code"] == "LATEST_CONTROL_INSUFFICIENT_TRADES"
