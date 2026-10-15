"""S7: objectively compare an evidenced hypothesis against its unchanged control.

Development-only, same prices/costs/capital. A matched direction is not proof
of causation or independent profitability. Unverified/generated Python forbidden.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isclose
from typing import Any, Literal

from core.backtest.engine import Trade
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


SUPPORTED_CONTROLLED_METRICS = frozenset(
    {"total_return", "cagr", "max_drawdown", "sharpe", "sortino", "trade_count"}
)


@dataclass(frozen=True)
class ExecutionDelta:
    """Calendar-matched executions, not inferred trade-level causal attribution."""

    matched_event_count: int
    added_event_count: int
    removed_event_count: int
    resized_event_count: int
    execution_timing_changed: bool
    parent_costs: float
    child_costs: float
    event_samples: tuple[dict[str, Any], ...]
    evidence_scope: Literal["OBSERVED_FILLS_NO_CAUSAL_INFERENCE"] = (
        "OBSERVED_FILLS_NO_CAUSAL_INFERENCE"
    )


@dataclass(frozen=True)
class DevelopmentWindow:
    """Descriptive fixed four-way partition, NOT a separate holdout or PIT test."""

    start_index: int
    end_index: int
    start_time: str
    end_time: str
    parent_total_return: float
    child_total_return: float
    total_return_delta: float
    parent_max_drawdown: float
    child_max_drawdown: float
    validation_scope: Literal["REUSED_DEVELOPMENT"] = "REUSED_DEVELOPMENT"


def _execution_delta(parent: AcademicDevelopmentResult,
                     child: AcademicDevelopmentResult) -> ExecutionDelta:
    def index(trades: tuple[Trade, ...]) -> dict[tuple[str, str, str], Trade]:
        result: dict[tuple[str, str, str], Trade] = {}
        for trade in trades:
            key = (trade.timestamp, trade.side, trade.symbol)
            if key in result:
                raise ControlledExperimentError("multiple identical execution keys unsupported")
            result[key] = trade
        return result

    before, after = index(parent.trades), index(child.trades)
    common = sorted(before.keys() & after.keys())
    removed = sorted(before.keys() - after.keys())
    added = sorted(after.keys() - before.keys())
    events: list[dict[str, Any]] = []
    resized = 0
    for key in common:
        initial, changed = before[key], after[key]
        if not isclose(initial.quantity, changed.quantity, rel_tol=1e-10, abs_tol=1e-10):
            resized += 1
            events.append({
                "timestamp": key[0], "side": key[1], "symbol": key[2],
                "event_kind": "RESIZED", "parent_quantity": initial.quantity,
                "child_quantity": changed.quantity, "parent_cost": initial.cost,
                "child_cost": changed.cost,
            })
    for key, source, kind in ((k, before, "REMOVED") for k in removed):
        event = source[key]
        events.append({
            "timestamp": key[0], "side": key[1], "symbol": key[2],
            "event_kind": kind, "parent_quantity": event.quantity,
            "child_quantity": None, "parent_cost": event.cost, "child_cost": None,
        })
    for key in added:
        event = after[key]
        events.append({
            "timestamp": key[0], "side": key[1], "symbol": key[2],
            "event_kind": "ADDED", "parent_quantity": None,
            "child_quantity": event.quantity, "parent_cost": None,
            "child_cost": event.cost,
        })
    events.sort(key=lambda e: (e["timestamp"], e["side"], e["event_kind"]))
    return ExecutionDelta(
        matched_event_count=len(common),
        added_event_count=len(added), removed_event_count=len(removed),
        resized_event_count=resized,
        execution_timing_changed=bool(added or removed),
        parent_costs=parent.total_paid_costs, child_costs=child.total_paid_costs,
        event_samples=tuple(events[:16]),
    )


def _development_windows(
    parent: AcademicDevelopmentResult,
    child: AcademicDevelopmentResult,
    market: MarketDataSet,
) -> tuple[DevelopmentWindow, ...]:
    points = len(market.bars) - 1
    if (points < 4 or len(parent.equity_curve) != len(market.bars)
            or len(child.equity_curve) != len(market.bars)):
        raise ControlledExperimentError("insufficient aligned equity for development windows")
    offsets = tuple(points * i // 4 for i in range(5))
    windows: list[DevelopmentWindow] = []
    for start, end in zip(offsets[:-1], offsets[1:], strict=True):
        control = calculate_metrics(parent.equity_curve[start:end + 1], (),
                                    periods_per_year=252.0)
        changed = calculate_metrics(child.equity_curve[start:end + 1], (),
                                    periods_per_year=252.0)
        windows.append(DevelopmentWindow(
            start_index=start, end_index=end,
            start_time=market.bars[start].timestamp.isoformat(),
            end_time=market.bars[end].timestamp.isoformat(),
            parent_total_return=control.total_return,
            child_total_return=changed.total_return,
            total_return_delta=changed.total_return - control.total_return,
            parent_max_drawdown=control.max_drawdown,
            child_max_drawdown=changed.max_drawdown,
        ))
    return tuple(windows)


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
    execution_delta: ExecutionDelta
    development_windows: tuple[DevelopmentWindow, ...]
    causal_status: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"


@dataclass(frozen=True)
class ControlledExperimentReport:
    dataset_hash: str
    audit_hash: str
    diagnostic_proposal_hash: str
    plan_hash: str
    experiments: tuple[ControlledOutcome, ...]
    evidence_hash: str
    multiple_comparison_notice: bool
    status: Literal["CONTROLLED_DEVELOPMENT_COMPARISON"] = (
        "CONTROLLED_DEVELOPMENT_COMPARISON"
    )
    out_of_sample_approved: Literal[False] = False
    broker_executable: Literal[False] = False
    causal_status: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"


def _measured_metric(result: AcademicDevelopmentResult, key: str) -> float | None:
    if key == "trade_count":
        # This reviewed long-only adapter reports fills separately. Only a
        # completed entry/exit round trip counts as a closed trade, even if a
        # final buy is still open at the end of the development series.
        sides = tuple(trade.side for trade in result.trades)
        if any(side not in ("buy", "sell") for side in sides):
            raise ControlledExperimentError("unsupported trade side for trade_count")
        if sides and (
            sides[0] != "buy"
            or any(a == b for a, b in zip(sides, sides[1:], strict=False))
        ):
            raise ControlledExperimentError("unpaired fills for trade_count")
        return float(sum(side == "sell" for side in sides))
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
        if hypothesis.expected_metric not in SUPPORTED_CONTROLLED_METRICS:
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
            execution_delta=_execution_delta(parent, child),
            development_windows=_development_windows(parent, child, market),
        ))
    proof = {
        "schema": "s7-paired-development-v2",
        "dataset_hash": market.dataset_hash,
        "parent_audit_hash": audit.trace_hash,
        "parent_strategy_hash": parent.strategy_hash,
        "proposal_hash": validated.proposal_hash,
        "plan_hash": checked.plan_hash,
        "replay_hash": checked.compiled.replay.replay_hash,
        "costed_control_equity_hash": parent.equity_hash,
        "comparisons": [asdict(o) for o in measurements],
        "multiple_comparison_notice": len(measurements) > 1,
        "independent_oos": False,
    }
    return ControlledExperimentReport(
        dataset_hash=market.dataset_hash,
        audit_hash=audit.trace_hash,
        diagnostic_proposal_hash=validated.proposal_hash,
        plan_hash=checked.plan_hash,
        experiments=tuple(measurements),
        evidence_hash=content_hash(proof),
        multiple_comparison_notice=len(measurements) > 1,
    )
