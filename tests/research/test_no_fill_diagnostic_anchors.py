"""No-fill research must expose only actual hashed decision evidence, not fake trades."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    compile_algorithm_plan,
)
from research.llm.diagnostic_research import (
    DiagnosisContractError,
    approve_diagnostic_plan,
    build_diagnostic_context,
)
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


def _zero_fill_case(tmp_path: Path):
    market, catalog = _market(), _catalog(tmp_path)
    plan = AlgorithmPlan.model_validate({
        "plan_id": "unreachable_gate",
        "cases": [{
            "case_id": "out_of_range",
            "when": {
                "indicator_id": "parkinson_variance",
                "op": "greater_than",
                "threshold": 1000000,
            },
            "votes": [{"indicator_id": "time_series_momentum", "weight": 1}],
            "min_score": 0.5,
        }],
    })
    compiled = compile_algorithm_plan(catalog, plan, market)
    audit = audit_algorithm_plan(catalog, compiled, market)
    assert audit.evaluation.trades_count == 0
    assert not audit.fills
    return audit, compiled.compiled.strategy, market


def _diagnosis(context, parent, observed):
    return {
        "context_hash": context["context_hash"],
        "audit_hash": context["audit_hash"],
        "strategy_hash": context["strategy_hash"],
        "dataset_hash": context["dataset_hash"],
        "summary": ("No trades were entered. Compare an altered rule "
                    "against the fully inactive control."),
        "hypotheses": [{
            "hypothesis_id": "blocked_gate_study",
            "observed_ids": [observed],
            "mechanism": "The regime condition may block all eligible entry signals.",
            "alternative": "The entry vote might also be inactive even if the regime changes.",
            "expected_metric": "trade_count",
            "predicted_direction": "INCREASE",
            "test_design": "RULE_STRUCTURE",
            "control": "PARENT_UNCHANGED",
            "next_intent": {
                "mode": "structure",
                "parent_ids": [parent.strategy_id],
                "operations": [{
                    "op": "REPLACE_RULE", "path": "entry.conditions.0",
                    "condition": {
                        "left": "plan_vote_score", "op": "greater_than", "value": 0.2
                    },
                }],
                "rationale": "A predeclared one-rule test against the zero-fill baseline.",
            },
        }],
    }


def test_zero_fill_context_exposes_hashed_real_decision_refs_only(tmp_path: Path):
    audit, parent, _ = _zero_fill_case(tmp_path)
    before_hash = audit.trace_hash
    context = build_diagnostic_context(audit, parent)
    assert audit.trace_hash == before_hash
    assert context["observations"]["closed_trades"] == 0
    assert context["observations"]["execution_samples"] == []
    assert context["observations"]["loss_cases"] == []
    samples = context["observations"]["non_execution_decision_samples"]
    assert samples
    assert len(samples) <= 12
    actual_ids = {item.decision_id for item in audit.decisions}
    for sample in samples:
        assert sample["decision_id"] in actual_ids
        assert sample["decision_action"] in {
            "WARMUP", "FILTERED_REGIME", "NO_ENTRY_SIGNAL",
        }
        assert sample["fill_id"] is None
        assert sample["indicator_values"]
        assert sample["signal_time"]
        assert sample["evaluated_gates"]
    assert not context["validation_scope"].startswith("OOS")


def test_zero_fill_diagnosis_refs_bind_and_unrelated_ids_rejected(tmp_path: Path):
    audit, parent, _ = _zero_fill_case(tmp_path)
    context = build_diagnostic_context(audit, parent)
    observed = context["observations"]["non_execution_decision_samples"][0]["decision_id"]
    payload = _diagnosis(context, parent, observed)
    result = approve_diagnostic_plan(audit, parent, context, payload)
    assert result.experiments[0].observed_ids == (observed,)
    assert result.causal_claim == "UNTESTED_HYPOTHESIS"
    assert result.broker_executable is False
    forged = deepcopy(payload)
    forged["hypotheses"][0]["observed_ids"] = ["made_up_trade_1"]
    with pytest.raises(DiagnosisContractError, match="unknown audit observation"):
        approve_diagnostic_plan(audit, parent, context, forged)
    forged_context = deepcopy(context)
    forged_context["observations"]["non_execution_decision_samples"][0]["decision_id"] = (
        "fake_decision"
    )
    with pytest.raises(DiagnosisContractError, match="context was changed"):
        approve_diagnostic_plan(audit, parent, forged_context, payload)


def test_existing_nonzero_context_contract_is_byte_stable(tmp_path: Path):
    market, catalog = _market(), _catalog(tmp_path)
    compiled = compile_algorithm_plan(catalog, _plan(), market)
    audit = audit_algorithm_plan(catalog, compiled, market)
    assert audit.fills
    previous_packet = deepcopy(audit.llm_packet)
    previous_trace = audit.trace_hash
    context = build_diagnostic_context(audit, compiled.compiled.strategy)
    assert "non_execution_decision_samples" not in context["observations"]
    assert audit.llm_packet == previous_packet
    assert audit.trace_hash == previous_trace
