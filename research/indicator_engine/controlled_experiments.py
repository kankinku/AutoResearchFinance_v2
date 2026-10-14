"""S7: objectively compare an evidenced hypothesis against its unchanged control.

Development-only, same prices/costs/capital. A matched direction is not proof
of causation or independent profitability. Unverified/generated Python forbidden.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from research.indicator_engine.algorithm_plan import (
    CompiledAlgorithmPlan,
    audit_algorithm_plan,
    compile_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.strategy_adapter import (
    AcademicDevelopmentResult,
    evaluate_compiled_development,
)
from research.llm.diagnostic_research import (
    DiagnosisContractError,
    approve_diagnostic_plan,
    build_diagnostic_context,
)


class ControlledExperimentError(ValueError):
    """Unmeasurable or unverified controlled development experiment."""


_SUPPORTED = frozenset({"total_return", "cagr", "max_drawdown", "sharpe", "sortino"})


@dataclass(frozen=True)
class ControlledOutcome:
    hypothesis_id: str
    child_strategy_hash: str
    expected_direction: str
    metric: str
    parent_metric: float | None
    child_metric: float | None
    delta: float | None
    status: Literal[
        "NO_OBSERVED_EFFECT", "DIRECTION_MATCHED_DEVELOPMENT_ONLY",
        "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY", "METRIC_UNAVAILABLE",
    ]
    same_fill_trace: bool
    parent_fill_count: int
    child_fill_count: int
    parent_final_equity: float
    child_final_equity: float
    causal_status: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"


@dataclass(frozen=True)
class ControlledExperimentReport:
    dataset_hash: str
    audit_hash: str
    diagnostic_proposal_hash: str
    plan_hash: str
    experiments: tuple[ControlledOutcome, ...]
    evidence_hash: str
    status: Literal["CONTROLLED_DEVELOPMENT_COMPARISON"] = (
        "CONTROLLED_DEVELOPMENT_COMPARISON"
    )
    out_of_sample_approved: Literal[False] = False
    broker_executable: Literal[False] = False
    causal_status: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"


def _measured_metric(result: AcademicDevelopmentResult, key: str) -> float | None:
    measured = calculate_metrics(result.equity_curve, (), periods_per_year=252.0)
    val = getattr(measured, key)
    return None if val is None else float(val)


def compare_controlled_experiments(
    catalog: ResearchCatalog,
    compiled: CompiledAlgorithmPlan,
    market: MarketDataSet,
    diagnostic_response: dict[str, Any],
    *,
    initial_cash: float = 10_000.0,
) -> ControlledExperimentReport:
    """Recompute parent and typed child under identical development conditions.

    Raw GPT response must pass the full S2 evidence gate again. The source
    algorithm, feature vectors, input prices and cost version are recomputed.
    No OOS, no order permissions, and no unreviewed metric interpretation.
    """
    if market.zone != DataZone.DEVELOPMENT:
        raise ControlledExperimentError("only DEVELOPMENT data may enter comparisons")
    if not isinstance(diagnostic_response, dict):
        raise ControlledExperimentError("structured diagnostic response required")
    if not isinstance(compiled, CompiledAlgorithmPlan):
        raise ControlledExperimentError("typed compiled plan required")
    checked = compile_algorithm_plan(catalog, compiled.plan, market)
    if checked != compiled:
        raise ControlledExperimentError("compiled plan integrity mismatch")
    audit = audit_algorithm_plan(catalog, checked, market, initial_cash=initial_cash)
    context = build_diagnostic_context(audit, checked.compiled.strategy)
    try:
        validated = approve_diagnostic_plan(
            audit, checked.compiled.strategy, context, diagnostic_response,
        )
    except DiagnosisContractError as exc:
        raise ControlledExperimentError(
            "diagnostic identity or audit mismatch: " + str(exc)
        ) from exc
    for hypothesis in validated.experiments:
        if hypothesis.expected_metric not in _SUPPORTED:
            raise ControlledExperimentError(
                "unsupported metric for controlled comparison: " + hypothesis.expected_metric
            )
    parent = audit.evaluation
    measurements: list[ControlledOutcome] = []
    for hypothesis in validated.experiments:
        # The only modification is an S2-gated StrategyIR, with all original
        # academic vectors, time alignment, dataset hash and fees retained.
        child_compiled = replace(
            checked.compiled,
            strategy=hypothesis.child,
            strategy_hash=hypothesis.child_hash,
        )
        try:
            child = evaluate_compiled_development(
                child_compiled, market, initial_cash=initial_cash,
            )
        except (ValueError, ResearchCatalogError) as exc:
            raise ControlledExperimentError(
                "candidate could not run under canonical policy"
            ) from exc
        metric = hypothesis.expected_metric
        baseline = _measured_metric(parent, metric)
        candidate = _measured_metric(child, metric)
        identical = (parent.trades == child.trades and parent.equity_curve == child.equity_curve)
        delta = candidate - baseline if candidate is not None and baseline is not None else None
        if identical:
            state = "NO_OBSERVED_EFFECT"
        elif delta is None:
            state = "METRIC_UNAVAILABLE"
        elif (
            delta > 0 if hypothesis.predicted_direction == "INCREASE" else delta < 0
        ):
            state = "DIRECTION_MATCHED_DEVELOPMENT_ONLY"
        else:
            state = "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY"
        measurements.append(ControlledOutcome(
            hypothesis_id=hypothesis.hypothesis_id,
            child_strategy_hash=child.strategy_hash,
            expected_direction=hypothesis.predicted_direction,
            metric=metric,
            parent_metric=baseline,
            child_metric=candidate,
            delta=delta,
            status=state,  # type: ignore[arg-type]
            same_fill_trace=parent.trades == child.trades,
            parent_fill_count=parent.trades_count,
            child_fill_count=child.trades_count,
            parent_final_equity=parent.final_equity,
            child_final_equity=child.final_equity,
        ))
    proof = {
        "schema": "s7-paired-development-v1",
        "dataset_hash": market.dataset_hash,
        "parent_audit_hash": audit.trace_hash,
        "parent_strategy_hash": parent.strategy_hash,
        "proposal_hash": validated.proposal_hash,
        "plan_hash": checked.plan_hash,
        "replay_hash": checked.compiled.replay.replay_hash,
        "costed_control_equity_hash": parent.equity_hash,
        "comparisons": [asdict(o) for o in measurements],
        "independent_oos": False,
    }
    return ControlledExperimentReport(
        dataset_hash=market.dataset_hash,
        audit_hash=audit.trace_hash,
        diagnostic_proposal_hash=validated.proposal_hash,
        plan_hash=checked.plan_hash,
        experiments=tuple(measurements),
        evidence_hash=content_hash(proof),
    )
