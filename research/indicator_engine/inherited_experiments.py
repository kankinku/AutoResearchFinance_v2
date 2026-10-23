"""Counted-inheritance S7: paired canonical development study for actual StrategyIR.

Legacy AlgorithmPlan S7 is unchanged. Uses exactly the same audited
parent, frozen data, next-open fills, fees and S2 diagnosis approval.
"""

from __future__ import annotations

from dataclasses import asdict

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.controlled_experiments import (
    SUPPORTED_CONTROLLED_METRICS,
    ControlledExperimentError,
    ControlledExperimentReport,
    ControlledOutcome,
    _development_windows,
    _execution_delta,
    _measured_metric,
)
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.strategy_adapter import (
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)
from research.llm.diagnostic_research import (
    DiagnosisContractError,
    approve_diagnostic_plan,
    build_diagnostic_context,
)
from research.llm.inherited_feature_compiler import bind_inherited_features


def compare_inherited_experiments(
    parent_compiled: CompiledAcademicStrategy,
    market: MarketDataSet,
    diagnostic_response: dict[str, object],
    *,
    parent_proof_hash: str = "",
    initial_cash: float = 10_000.0,
) -> ControlledExperimentReport:
    """Only S2-authenticated, source-bound mutations can enter S7."""
    if market.zone != DataZone.DEVELOPMENT or not isinstance(diagnostic_response, dict):
        raise ControlledExperimentError("invalid inherited S7 context")
    audit = audit_inherited_decisions(parent_compiled, market, initial_cash=initial_cash)
    context = build_diagnostic_context(audit, parent_compiled.strategy)
    try:
        validated = approve_diagnostic_plan(
            audit,
            parent_compiled.strategy,
            context,
            diagnostic_response,
        )
    except DiagnosisContractError as exc:
        raise ControlledExperimentError("inherited diagnostic identity mismatch") from exc
    parent = audit.evaluation
    measurements: list[ControlledOutcome] = []
    for hypothesis in validated.experiments:
        if hypothesis.expected_metric not in SUPPORTED_CONTROLLED_METRICS:
            raise ControlledExperimentError("unsupported inherited S7 metric")
        candidate_compiled = bind_inherited_features(parent_compiled, hypothesis.child, market)
        try:
            child = evaluate_compiled_development(
                candidate_compiled,
                market,
                initial_cash=initial_cash,
            )
        except (ValueError, ResearchCatalogError) as exc:
            raise ControlledExperimentError("inherited child failed canonical replay") from exc
        metric = hypothesis.expected_metric
        original = _measured_metric(parent, metric)
        measured = _measured_metric(child, metric)
        delta = measured - original if measured is not None and original is not None else None
        identical = parent.trades == child.trades and parent.equity_curve == child.equity_curve
        if identical:
            state = "NO_OBSERVED_EFFECT"
        elif parent.trades_count > 0 and child.trades_count == 0:
            state = "DEGENERATE_INACTIVE_CHILD"
        elif delta is None:
            state = "METRIC_UNAVAILABLE"
        elif delta > 0 if hypothesis.predicted_direction == "INCREASE" else delta < 0:
            state = "DIRECTION_MATCHED_DEVELOPMENT_ONLY"
        else:
            state = "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY"
        measurements.append(
            ControlledOutcome(
                hypothesis_id=hypothesis.hypothesis_id,
                child_strategy_hash=child.strategy_hash,
                expected_direction=hypothesis.predicted_direction,
                metric=metric,
                parent_metric=original,
                child_metric=measured,
                delta=delta,
                status=state,  # type: ignore[arg-type]
                same_fill_trace=parent.trades == child.trades,
                parent_fill_count=parent.trades_count,
                child_fill_count=child.trades_count,
                parent_final_equity=parent.final_equity,
                child_final_equity=child.final_equity,
                execution_delta=_execution_delta(parent, child),
                development_windows=_development_windows(parent, child, market),
            )
        )
    plan_hash = content_hash(
        {
            "inherited_strategy": parent_compiled.strategy_hash,
            "parent_lineage_proof": parent_proof_hash,
        }
    )
    proof = {
        "schema": "s7-paired-inherited-development-v1",
        "dataset_hash": market.dataset_hash,
        "parent_audit_hash": audit.trace_hash,
        "parent_strategy_hash": parent.strategy_hash,
        "proposal_hash": validated.proposal_hash,
        "plan_hash": plan_hash,
        "replay_hash": parent_compiled.replay.replay_hash,
        "costed_control_equity_hash": parent.equity_hash,
        "comparisons": [asdict(x) for x in measurements],
        "multiple_comparison_notice": len(measurements) > 1,
        "independent_oos": False,
    }
    return ControlledExperimentReport(
        dataset_hash=market.dataset_hash,
        audit_hash=audit.trace_hash,
        diagnostic_proposal_hash=validated.proposal_hash,
        plan_hash=plan_hash,
        experiments=tuple(measurements),
        evidence_hash=content_hash(proof),
        multiple_comparison_notice=len(measurements) > 1,
    )
