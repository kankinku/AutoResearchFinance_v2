"""S7: frozen-control experiments must measure instead of assert causation."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from research.indicator_engine.algorithm_plan import (
    audit_algorithm_plan,
    compile_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.controlled_experiments import (
    ControlledExperimentError,
    compare_controlled_experiments,
)
from research.llm.diagnostic_research import build_diagnostic_context
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


def _inputs(tmp_path: Path, *, op: str = "REMOVE_REGIME_FILTER"):
    catalog, market = _catalog(tmp_path), _market()
    compiled = compile_algorithm_plan(catalog, _plan(), market)
    audit = audit_algorithm_plan(catalog, compiled, market)
    context = build_diagnostic_context(audit, compiled.compiled.strategy)
    if op == "REMOVE_REGIME_FILTER":
        operations = [{"op": "REMOVE_REGIME_FILTER", "path": "regime_filters.0"}]
        metric, direction = "total_return", "INCREASE"
    else:
        operations = [
            {"op": "CHANGE_POSITION_SIZE", "path": "risk.position_size_pct", "value": 70.0}
        ]
        metric, direction = "max_drawdown", "DECREASE"
    payload = {
        "context_hash": context["context_hash"],
        "audit_hash": context["audit_hash"],
        "strategy_hash": context["strategy_hash"],
        "dataset_hash": context["dataset_hash"],
        "summary": "Test a single competing explanation using fixed control conditions.",
        "hypotheses": [{
            "hypothesis_id": "test_regime_or_risk_01",
            "observed_ids": [context["observations"]["execution_samples"][0]["trade_id"]],
            "mechanism": "A binary regime rule or allocation could cause unwanted losses.",
            "alternative": "Removing the rule or reducing capital may lower gains too.",
            "expected_metric": metric,
            "predicted_direction": direction,
            "test_design": "ABLATION" if op == "REMOVE_REGIME_FILTER" else "PARAMETER",
            "control": "PARENT_UNCHANGED",
            "next_intent": {
                "mode": "structure" if op == "REMOVE_REGIME_FILTER" else "parameter",
                "parent_ids": [compiled.compiled.strategy.strategy_id],
                "operations": operations,
                "rationale": "Compare the changed rule to the frozen unmodified parent.",
            },
        }],
    }
    return catalog, compiled, market, payload


def test_controlled_ablation_measurement_reports_null_effect(tmp_path: Path):
    catalog, compiled, market, payload = _inputs(tmp_path)
    outcome = compare_controlled_experiments(catalog, compiled, market, payload)
    assert outcome.status == "CONTROLLED_DEVELOPMENT_COMPARISON"
    assert outcome.dataset_hash == market.dataset_hash
    assert outcome.audit_hash == payload["audit_hash"]
    assert len(outcome.experiments) == 1
    experiment = outcome.experiments[0]
    assert experiment.hypothesis_id == payload["hypotheses"][0]["hypothesis_id"]
    assert experiment.status == "NO_OBSERVED_EFFECT"
    assert experiment.delta == pytest.approx(0)
    assert experiment.parent_metric == experiment.child_metric
    assert experiment.same_fill_trace is True
    assert experiment.causal_status == "NOT_ESTABLISHED"
    assert outcome.out_of_sample_approved is False
    assert outcome.broker_executable is False
    assert compare_controlled_experiments(catalog, compiled, market, payload) == outcome


def test_risk_ablation_can_have_measured_difference_not_causal_proof(tmp_path: Path):
    catalog, compiled, market, payload = _inputs(tmp_path, op="CHANGE_POSITION_SIZE")
    outcome = compare_controlled_experiments(catalog, compiled, market, payload)
    experiment = outcome.experiments[0]
    assert experiment.metric == "max_drawdown"
    assert experiment.child_metric is not None and experiment.parent_metric is not None
    assert experiment.child_metric < experiment.parent_metric
    assert experiment.delta == pytest.approx(experiment.child_metric - experiment.parent_metric)
    assert experiment.status == "DIRECTION_MATCHED_DEVELOPMENT_ONLY"
    assert experiment.same_fill_trace is False
    assert outcome.evidence_hash
    assert experiment.causal_status == "NOT_ESTABLISHED"


def test_controlled_experiments_fail_closed_on_forged_evidence_or_market(tmp_path: Path):
    catalog, compiled, market, payload = _inputs(tmp_path)
    changed = deepcopy(payload)
    changed["audit_hash"] = "0" * 64
    with pytest.raises((ControlledExperimentError, ValueError), match="identit|mismatch|audit"):
        compare_controlled_experiments(catalog, compiled, market, changed)
    changed = deepcopy(payload)
    changed["hypotheses"][0]["observed_ids"] = ["fabricated-trade"]
    with pytest.raises((ControlledExperimentError, ValueError), match="unknown"):
        compare_controlled_experiments(catalog, compiled, market, changed)
    with pytest.raises(
        (ControlledExperimentError, ResearchCatalogError), match="data|replay|integrity"
    ):
        compare_controlled_experiments(catalog, compiled, _market(change_last=True), payload)
    bad = replace(compiled, plan=compiled.plan.model_copy(update={"plan_id": "forged"}))
    with pytest.raises(
        (ControlledExperimentError, ResearchCatalogError), match="integrity|mismatch"
    ):
        compare_controlled_experiments(catalog, bad, market, payload)


def test_unsupported_metric_is_not_pretended_tested(tmp_path: Path):
    catalog, compiled, market, payload = _inputs(tmp_path)
    payload["hypotheses"][0]["expected_metric"] = "win_rate"
    with pytest.raises(ControlledExperimentError, match="unsupported"):
        compare_controlled_experiments(catalog, compiled, market, payload)
