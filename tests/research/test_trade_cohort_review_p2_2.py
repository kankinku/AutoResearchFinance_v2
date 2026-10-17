"""P2-2: Whole development cohort; causal claims never authorized."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from core.integrity.hashes import content_hash
from research.indicator_engine.decision_audit import audit_compiled_academic_decisions
from research.llm.loss_attribution import LossAttributionError
from research.llm.trade_cohort_review import (
    _entry_regime,
    build_trade_cohort_review,
    link_completed_s7_to_cohort,
)
from tests.research.test_academic_decision_audit import _fixture


def test_all_closed_trades_and_one_to_one_matching(tmp_path: Path) -> None:
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    report = build_trade_cohort_review(audit, market)
    assert report == build_trade_cohort_review(audit, market)
    assert report["source_audit_hash"] == audit.trace_hash
    assert report["closed_trades"] == len(audit.round_trips)
    assert report["wins"] + report["losses"] + report["flats"] == len(audit.round_trips)
    assert sum(c["wins"] for c in report["cohorts"]) == report["wins"]
    assert sum(c["losses"] for c in report["cohorts"]) == report["losses"]
    assert report["matched_pair_count"] <= min(report["wins"], report["losses"], 8)
    assert report["unmatched_loss_count"] + report["matched_pairs_total"] == report["losses"]
    assert (
        report["undisplayed_matched_pairs"] + report["matched_pair_count"]
        == report["matched_pairs_total"]
    )
    assert (
        len({p["win_trade_id"] for p in report["matched_example_pairs"]})
        == report["matched_pair_count"]
    )
    assert report["entry_regime_definition"]
    assert report["regime_asof"] == "PRE_ENTRY_SIGNAL_BAR_CLOSE_ONLY"
    assert report["statistical_significance"] == "NOT_ESTABLISHED"
    assert report["independent_oos_approved"] is False
    for observation in report["indicator_observation_frequencies"]:
        assert 0 <= observation["losing_trades_with_code"] <= report["losses"]
        assert 0 <= observation["winning_trades_with_code"] <= report["wins"]
        assert observation["not_proven_predictive"] is True
    for pair in report["matched_example_pairs"]:
        assert pair["not_causal_matching"] is True
    once = build_trade_cohort_review(audit, market, max_pairs=1)
    assert once["matched_pair_count"] <= 1
    assert once["matched_pairs_total"] == report["matched_pairs_total"]


def test_entry_regime_never_uses_future_bars(tmp_path: Path) -> None:
    market, _ = _fixture(tmp_path)
    original = _entry_regime(market, 100)
    last = market.bars[-1]
    modified = replace(
        market,
        bars=(*market.bars[:-1], replace(last, close=last.close * 2, high=last.close * 2 + 1)),
    )
    assert original == _entry_regime(modified, 100)
    assert _entry_regime(market, 19) == ("WARMUP_UNKNOWN", "WARMUP_UNKNOWN")


def test_malformed_audit_fails_before_analysis(tmp_path: Path) -> None:
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    with pytest.raises(LossAttributionError):
        build_trade_cohort_review(replace(audit, trace_hash="a" * 64), market)
    with pytest.raises(LossAttributionError):
        build_trade_cohort_review(audit, market, max_pairs=0)


def test_s7_join_fails_closed_without_matching_ancestors(tmp_path: Path) -> None:
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    hypothesis = "h-test"
    original = {
        "generation": 1,
        "evidence_hash": "a" * 64,
        "audit_hash": audit.trace_hash,
        "strategy_hash": audit.evaluation.strategy_hash,
        "experiments": [
            {
                "hypothesis_id": hypothesis,
                "observed_ids": [audit.round_trips[0].trade_id],
                "mechanism": "Test whether entry filters remove losing trades.",
                "alternative": "Entry gating also removes profitable trade signals.",
                "test_design": "ABLATION",
                "expected_metric": "trade_count",
                "predicted_direction": "DECREASE",
                "proposal_child_hash": "c" * 64,
            }
        ],
    }
    trial = {
        "hypothesis_id": hypothesis,
        "child_strategy_hash": "c" * 64,
        "causal_status": "NOT_ESTABLISHED",
        "expected_direction": "DECREASE",
        "metric": "trade_count",
        "status": "DIRECTION_MATCHED_DEVELOPMENT_ONLY",
        "parent_final_equity": audit.evaluation.final_equity,
        "child_final_equity": audit.evaluation.final_equity - 100,
        "execution_delta": {"parent_costs": 20.0, "child_costs": 16.0},
    }
    doc = {
        "generation": 1,
        "original_generation_evidence_hash": "a" * 64,
        "study_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        "report": {
            "causal_status": "NOT_ESTABLISHED",
            "out_of_sample_approved": False,
            "broker_executable": False,
            "dataset_hash": audit.evaluation.dataset_hash,
            "audit_hash": audit.trace_hash,
            "experiments": [trial],
        },
    }
    record = {**doc, "record_hash": content_hash(doc)}
    good = link_completed_s7_to_cohort(audit, original, record)
    assert good["linked_experiments"][0]["economic_direction"] == "WORSE"
    assert good["linked_experiments"][0]["predicted_direction_status"].startswith(
        "DIRECTION_MATCHED"
    )
    assert good["linked_experiments"][0]["causal_status"] == "NOT_ESTABLISHED"
    assert (
        link_completed_s7_to_cohort(audit, original, None)["status"]
        == "NO_MEASURED_S7_FOR_GENERATION"
    )
    invalid = deepcopy(record)
    invalid["report"]["experiments"][0]["child_final_equity"] += 1
    with pytest.raises(LossAttributionError, match="hash"):
        link_completed_s7_to_cohort(audit, original, invalid)
    fake = deepcopy(original)
    fake["experiments"][0]["observed_ids"] = ["invented-trade"]
    with pytest.raises(LossAttributionError, match="grounded"):
        link_completed_s7_to_cohort(audit, fake, record)


def test_gateway_next_plan_receives_cohort_and_verified_s7(tmp_path: Path) -> None:
    from tests.integrations.test_academic_mcp_sessions import _setup
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    server, started = _setup(tmp_path)
    assert "trade_cohort_review" not in started["model_context"]
    model = ScriptedResearcher()
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": model.propose(started["model_context"]),
        },
    )
    done = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": model.propose(staged["model_context"]),
        },
    )
    assert done["completed_generations"] == 1
    cohort = done["model_context"]["trade_cohort_review"]
    linked = done["model_context"]["paired_s7_evidence_link"]
    assert cohort["source_audit_hash"] == done["history"][-1]["audit_hash"]
    assert linked["source_audit_hash"] == cohort["source_audit_hash"]
    assert linked["no_causal_inference"] is True
    assert done["history"][-1]["diagnostic_context_hash"] == staged["model_context"]["context_hash"]
    assert done["orders_enabled"] is False
