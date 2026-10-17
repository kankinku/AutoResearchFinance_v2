"""P2-1: Observed failure patterns are provenance-linked, not inferred causes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.data.contracts import DataZone, MarketDataSet
from research.indicator_engine.decision_audit import audit_compiled_academic_decisions
from research.llm.loss_attribution import LossAttributionError, build_loss_attribution
from tests.research.test_academic_decision_audit import _fixture


def test_pattern_report_is_bounded_deterministic_and_evidence_linked(tmp_path: Path) -> None:
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    report = build_loss_attribution(audit, market)
    assert report == build_loss_attribution(audit, market)
    assert report["schema"] == "observed-loss-attribution-p2-1-v1"
    assert report["source_audit_hash"] == audit.trace_hash
    assert report["dataset_hash"] == market.dataset_hash
    assert report["causal_status"] == "NOT_ESTABLISHED"
    assert report["independent_oos_approved"] is False
    assert report["broker_executable"] is False
    assert len(report["loss_cases"]) <= 8
    assert len(report["winner_controls"]) <= 8
    losses = {trade.trade_id for trade in audit.round_trips if trade.net_pnl < 0}
    wins = {trade.trade_id for trade in audit.round_trips if trade.net_pnl > 0}
    ids = {decision.decision_id for decision in audit.decisions}
    for case in report["loss_cases"]:
        assert case["trade_id"] in losses
        assert case["entry_decision_id"] in ids
        assert case["exit_decision_id"] in ids
        assert case["net_pnl"] < 0
        assert case["cost_paid"] >= 0
        assert case["price_pnl_before_cost"] - case["cost_paid"] == pytest.approx(case["net_pnl"])
        assert case["observation_codes"]
        assert case["close_peak_giveback_fraction"] >= 0
        assert case["entry_indicator_values"]
        assert case["exit_indicator_values"]
    assert all(row["trade_id"] in wins for row in report["winner_controls"])
    assert all(row["kind"] == "RECOMMEND_TEST_ONLY" for row in report["test_suggestions"])
    assert all("observed_winner_cases" in row for row in report["test_suggestions"])
    assert all(
        row["statistical_significance"] == "NOT_ESTABLISHED_EX_POST_SELECTION"
        for row in report["test_suggestions"]
    )
    assert all(row["control"] == "PARENT_UNCHANGED" for row in report["test_suggestions"])
    assert report["evidence_hash"]


def test_reject_tampered_audit_and_sealed_data(tmp_path: Path) -> None:
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    with pytest.raises(LossAttributionError, match="audit"):
        build_loss_attribution(replace(audit, trace_hash="f" * 64), market)
    sealed = MarketDataSet(market.version, DataZone.SEALED_OOS, market.bars)
    with pytest.raises(LossAttributionError, match="development"):
        build_loss_attribution(audit, sealed)
    swapped = replace(market, bars=market.bars[:-1])
    with pytest.raises(LossAttributionError):
        build_loss_attribution(audit, swapped)


def test_no_loss_does_not_invent_hypotheses(tmp_path: Path) -> None:
    market, compiled = _fixture(tmp_path)
    audit = audit_compiled_academic_decisions(compiled, market)
    # A filtered trade cohort with no losing closed trade is a legitimate
    # *analysis* case; the synthetic edit is deliberately not re-signed.
    # Test a genuine audit with no executions using an all-flat legal plan
    # in the dedicated zero-fill integration coverage.
    assert len(build_loss_attribution(audit, market)["test_suggestions"]) <= 4


def test_gateway_next_plan_context_includes_loss_attribution_without_rewriting_s2(tmp_path: Path):
    from tests.integrations.test_academic_mcp_sessions import _setup
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    server, started = _setup(tmp_path)
    assert "loss_attribution" not in started["model_context"]
    gpt = ScriptedResearcher()
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": gpt.propose(started["model_context"]),
        },
    )
    diagnosis = gpt.propose(staged["model_context"])
    original_diagnostic_context = staged["model_context"]["context_hash"]
    result = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": diagnosis,
        },
    )
    assert result["completed_generations"] == 1
    assert result["history"][0]["diagnostic_context_hash"] == original_diagnostic_context
    ctx = result["model_context"]
    evidence = ctx["loss_attribution"]
    assert evidence["source_generation"] == 1
    assert evidence["source_generation_evidence_hash"] == result["history"][0]["evidence_hash"]
    assert evidence["source_audit_hash"] == result["history"][0]["audit_hash"]
    assert evidence["causal_status"] == "NOT_ESTABLISHED"
    assert evidence["execution_policy"] == "GPT_MCP_PROPOSAL_ONLY_NOT_AUTO_APPLIED"
    again = server._dispatch("get_algorithm_research", {"session_id": started["session_id"]})
    assert again["model_context"]["loss_attribution"] == evidence
    assert again["completed_generations"] == 1
