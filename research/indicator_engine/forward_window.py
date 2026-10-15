"""Research-only chronological forward window using *past* bars solely as warmup.

The same immutable canonical BacktestEngine performs all executions. The
warmup portion is cash-only; returned performance starts with the first
holdout bar. Nothing in this module approves sealed OOS, PIT or orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Literal

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.strategy_adapter import evaluate_compiled_development
from research.indicator_engine.validation_gate import forward_research_blockers


@dataclass(frozen=True)
class ForwardWindowReport:
    plan_hash: str
    training_hash: str
    holdout_hash: str
    combined_hash: str
    evaluated_strategy_hash: str
    evaluation_hash: str
    holdout_start: str
    holdout_end: str
    warmup_bars: int
    holdout_bars: int
    initial_cash: float
    first_holdout_equity: float
    final_equity: float
    total_return: float
    cagr: float
    sharpe: float | None
    max_drawdown: float
    completed_trades: int
    fill_count: int
    paid_costs: float
    first_execution_time: str | None
    raw_close_to_close_buy_hold: float
    descriptive_gate_met: bool
    validation_blocking_reasons: tuple[str, ...]
    validation_decision: Literal["NOT_VALIDATED"] = "NOT_VALIDATED"
    status: Literal["NON_PIT_CHRONOLOGICAL_RESEARCH_ONLY"] = (
        "NON_PIT_CHRONOLOGICAL_RESEARCH_ONLY"
    )
    point_in_time_independently_verified: Literal[False] = False
    independent_oos_approved: Literal[False] = False
    candidate_promotable: Literal[False] = False
    broker_executable: Literal[False] = False


def evaluate_chronological_window(
    catalog: ResearchCatalog,
    plan: AlgorithmPlan,
    historical: MarketDataSet,
    forward: MarketDataSet,
    *,
    initial_cash: float = 10_000.0,
    max_warmup_bars: int = 300,
) -> ForwardWindowReport:
    """Evaluate with no pre-forward cash gain, position, pending fill or decision.

    The signal history is compiled on (historical tail + forward) as one causal
    series. First forward day's *completed-close* decision may execute on the
    NEXT forward opening bar, never on the history's final or forward first open.

    Source hashes are recorded separately. The merged dataset has *no* source
    provenance because provider snapshots have distinct metadata. The result is
    intentionally development/non-PIT, even when periods are disjoint.
    """
    if (
        historical.zone != DataZone.DEVELOPMENT
        or forward.zone != DataZone.DEVELOPMENT
        or historical.timeframe != forward.timeframe
        or historical.calendar != forward.calendar
        or historical.timeframe != "1d"
        or historical.calendar != "us_equities"
    ):
        raise ResearchCatalogError("chronological evaluation requires matching DEVELOPMENT 1d")
    if not historical.bars or len(forward.bars) < 3:
        raise ResearchCatalogError("insufficient chronological input rows")
    if (historical.provenance is None) != (forward.provenance is None):
        raise ResearchCatalogError("mixed data lineage is forbidden across the boundary")
    if historical.provenance is not None and forward.provenance is not None:
        if (
            historical.provenance.source_id != forward.provenance.source_id
            or historical.provenance.corporate_action_policy
            != forward.provenance.corporate_action_policy
        ):
            raise ResearchCatalogError("price vendor or adjustment policy differs at boundary")
    histories = {bar.symbol for bar in historical.bars}
    futures = {bar.symbol for bar in forward.bars}
    if len(histories) != 1 or histories != futures:
        raise ResearchCatalogError("single matching symbol required for forward evaluation")
    start: datetime = forward.bars[0].timestamp
    if historical.bars[-1].timestamp >= start:
        raise ResearchCatalogError("training rows must strictly precede the forward boundary")
    if type(max_warmup_bars) is not int or max_warmup_bars <= 0:
        raise ResearchCatalogError("positive bounded warmup count required")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ResearchCatalogError("positive finite research cash required")

    # Registered lookbacks are fixed; verify the actual (not caller-claimed)
    # warmup coverage. A 300-bar cap is adequate for the seeded 252-bar family.
    indicators = {
        case.when.indicator_id for case in plan.cases
    } | {
        vote.indicator_id for case in plan.cases for vote in case.votes
    }
    required = max(catalog.get_indicator(name).lookback for name in indicators) + 1
    width = min(len(historical.bars), max_warmup_bars)
    if width < required:
        raise ResearchCatalogError("insufficient past-only bars for verified indicator warmup")
    prefix = historical.bars[-width:]
    # A standalone development data identity is used for computational replay.
    # Hashes for each historical vendor dataset remain independently auditable.
    merged = MarketDataSet(
        version="academic-forward-window-v1",
        zone=DataZone.DEVELOPMENT,
        bars=(*prefix, *forward.bars),
        timeframe=forward.timeframe,
        calendar=forward.calendar,
        provenance=None,
    )
    compiled = compile_algorithm_plan(catalog, plan, merged)
    result = evaluate_compiled_development(
        compiled.compiled, merged, initial_cash=initial_cash,
        signal_start_at=start,
    )
    if any(value != initial_cash for value in result.equity_curve[:width]):
        raise ResearchCatalogError("historical warmup changed portfolio equity")
    curve = result.equity_curve[width:]
    if len(curve) != len(forward.bars) or curve[0] != initial_cash:
        raise ResearchCatalogError("forward window did not start at uninvested cash")
    for fill in result.trades:
        if datetime.fromisoformat(fill.timestamp) <= start:
            raise ResearchCatalogError("execution on or before first forward close")
    metrics = calculate_metrics(curve, (), periods_per_year=252.0)
    closed = sum(fill.side == "sell" for fill in result.trades)
    if any(fill.side not in {"buy", "sell"} for fill in result.trades):
        raise ResearchCatalogError("unsupported fill side")
    first_execution = result.trades[0].timestamp if result.trades else None
    blocking_reasons = forward_research_blockers(
        historical, forward, cumulative_return=metrics.total_return,
        sharpe=metrics.sharpe, max_drawdown=metrics.max_drawdown,
        closed_trades=closed,
    )
    proof = {
        "schema": "academic-forward-window-v2",
        "plan_hash": compiled.plan_hash,
        "training_hash": historical.dataset_hash,
        "holdout_hash": forward.dataset_hash,
        "combined_hash": merged.dataset_hash,
        "strategy_hash": compiled.compiled.strategy_hash,
        "warmup_bars": width,
        "holdout_start": start.isoformat(),
        "initial_cash": initial_cash,
        "forward_equity": curve,
        "fills": [t.__dict__ for t in result.trades],
        "data_status": "NON_PIT_DEVELOPMENT",
        "validation_blocking_reasons": blocking_reasons,
    }
    return ForwardWindowReport(
        plan_hash=compiled.plan_hash,
        training_hash=historical.dataset_hash,
        holdout_hash=forward.dataset_hash,
        combined_hash=merged.dataset_hash,
        evaluated_strategy_hash=compiled.compiled.strategy_hash,
        evaluation_hash=content_hash(proof),
        holdout_start=start.isoformat(),
        holdout_end=forward.bars[-1].timestamp.isoformat(),
        warmup_bars=width,
        holdout_bars=len(forward.bars),
        initial_cash=initial_cash,
        first_holdout_equity=curve[0],
        final_equity=curve[-1],
        total_return=metrics.total_return,
        cagr=metrics.cagr,
        sharpe=metrics.sharpe,
        max_drawdown=metrics.max_drawdown,
        completed_trades=closed,
        fill_count=len(result.trades),
        paid_costs=result.total_paid_costs,
        first_execution_time=first_execution,
        raw_close_to_close_buy_hold=(
            forward.bars[-1].close / forward.bars[0].close - 1.0
        ),
        descriptive_gate_met=(
            metrics.total_return > 0 and metrics.max_drawdown <= 0.20
            and closed >= 10 and metrics.sharpe is not None
            and metrics.sharpe > 0.50
        ),
        validation_blocking_reasons=blocking_reasons,
    )
