"""Ex-post period robustness for a FROZEN typed AlgorithmPlan on DEVELOPMENT QQQ.

This deliberately does NOT constitute walk-forward model selection, PIT validation,
sealed OOS, or live proof. The plan may already have seen every year. Only a
time-of-selection isolated RESEARCH RUN can certify train-before-test selection.
No generation counts or parent choices are changed by these diagnostics.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from typing import Literal

from core.data.contracts import Bar, DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import AlgorithmPlan
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.development_benchmark import (
    compare_qqq_development_benchmarks,
)
from research.indicator_engine.forward_window import evaluate_chronological_window


@dataclass(frozen=True)
class HistoricalPeriod:
    year: int
    period_first: str
    period_last: str
    year_end_coverage: Literal["YEAR_END_OBSERVED", "PARTIAL_YEAR"]
    trading_bars: int
    initial_cash: float
    first_holdout_equity: float
    final_equity: float
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe: float | None
    completed_trades: int
    fill_count: int
    paid_costs: float
    first_fill: str | None
    market_qqq_costed_return: float
    excess_costed_return: float
    evaluation_hash: str
    benchmark_hash: str


@dataclass(frozen=True)
class HistoricalRobustnessReport:
    plan_hash: str
    development_hash: str
    development_cutoff: str
    periods: tuple[HistoricalPeriod, ...]
    report_hash: str
    selection_scope: Literal[
        "PLAN_FROZEN_EX_POST_NOT_WALKFORWARD_SELECTION"
    ] = "PLAN_FROZEN_EX_POST_NOT_WALKFORWARD_SELECTION"
    status: Literal[
        "EX_POST_DEVELOPMENT_ROBUSTNESS_ONLY"
    ] = "EX_POST_DEVELOPMENT_ROBUSTNESS_ONLY"
    independent_oos_approved: Literal[False] = False
    candidate_promotable: Literal[False] = False
    broker_executable: Literal[False] = False


def _segment(market: MarketDataSet, bars: tuple[Bar, ...], suffix: str) -> MarketDataSet:
    return MarketDataSet(
        version=market.version + "-" + suffix,
        zone=DataZone.DEVELOPMENT,
        bars=bars,
        timeframe=market.timeframe,
        calendar=market.calendar,
        provenance=market.provenance,
    )


def evaluate_historical_robustness(
    catalog: ResearchCatalog,
    plan: AlgorithmPlan,
    market: MarketDataSet,
    *,
    years: Sequence[int],
    last_development_date: date,
    initial_cash: float = 10_000.0,
    max_warmup_bars: int = 300,
    min_period_bars: int = 30,
) -> HistoricalRobustnessReport:
    """Apply the same preselected plan to multiple chronological annual slices.

    Warmup is cash-only; each annual diagnostic starts with its own cash,
    and the benchmark enters on the same first *next-open* opportunity.
    Results are *ex-post diagnostics*, never held-out strategy discovery.
    A caller must name its allowed last DEVELOPMENT date explicitly.
    """
    if (
        market.zone != DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or not market.bars
        or any(bar.symbol != "QQQ" for bar in market.bars)
    ):
        raise ResearchCatalogError("QQQ daily development dataset required")
    if not isinstance(last_development_date, date) or isinstance(last_development_date, datetime):
        raise ResearchCatalogError("explicit development cutoff date required")
    if market.bars[-1].timestamp.date() > last_development_date:
        raise ResearchCatalogError("data past development cutoff is forbidden")
    if any(
        previous.timestamp >= current.timestamp
        for previous, current in zip(market.bars, market.bars[1:], strict=False)
    ):
        raise ResearchCatalogError("ordered unique daily timestamps required")
    if (
        not years
        or any(type(y) is not int for y in years)
        or tuple(years) != tuple(sorted(set(years)))
        or any(y > last_development_date.year for y in years)
    ):
        raise ResearchCatalogError("unique ascending development years required")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ResearchCatalogError("positive starting cash required")
    if type(min_period_bars) is not int or min_period_bars < 3:
        raise ResearchCatalogError("minimum annual trading bars invalid")

    slices: list[HistoricalPeriod] = []
    for year in years:
        left = next((index for index, bar in enumerate(market.bars)
                     if bar.timestamp.year >= year), len(market.bars))
        right = next((index for index, bar in enumerate(market.bars)
                      if bar.timestamp.year > year), len(market.bars))
        if left == 0 or right - left < min_period_bars:
            raise ResearchCatalogError("missing year or insufficient training warmup / bars")
        if market.bars[left].timestamp.year != year:
            raise ResearchCatalogError("missing year in development dataset")
        history = _segment(market, tuple(market.bars[:left]), f"history-before-{year}")
        forward = _segment(market, tuple(market.bars[left:right]), f"year-{year}")
        # The existing verified compiler uses previous bars for indicator warmup,
        # but its canonical execution engine cannot open before the first
        # completed forward close. All fills are next-bar opens.
        observed = evaluate_chronological_window(
            catalog, plan, history, forward,
            initial_cash=initial_cash,
            max_warmup_bars=max_warmup_bars,
        )
        benchmark = compare_qqq_development_benchmarks(
            forward, initial_cash=initial_cash
        )["qqq_costed_buy_and_hold"]
        y_last = forward.bars[-1].timestamp.date()
        slices.append(HistoricalPeriod(
            year=year,
            period_first=observed.holdout_start,
            period_last=observed.holdout_end,
            year_end_coverage=(
                "YEAR_END_OBSERVED" if y_last.month == 12 else "PARTIAL_YEAR"
            ),
            trading_bars=observed.holdout_bars,
            initial_cash=initial_cash,
            first_holdout_equity=observed.first_holdout_equity,
            final_equity=observed.final_equity,
            total_return=observed.total_return,
            cagr=observed.cagr,
            max_drawdown=observed.max_drawdown,
            sharpe=observed.sharpe,
            completed_trades=observed.completed_trades,
            fill_count=observed.fill_count,
            paid_costs=observed.paid_costs,
            first_fill=observed.first_execution_time,
            market_qqq_costed_return=benchmark["total_return"],
            excess_costed_return=observed.total_return - benchmark["total_return"],
            evaluation_hash=observed.evaluation_hash,
            benchmark_hash=benchmark["equity_curve_hash"],
        ))

    plan_hash = content_hash(plan.model_dump(mode="json"))
    digest = content_hash({
        "schema": "development-annual-ex-post-robustness-v1",
        "selection_scope": "PLAN_FROZEN_EX_POST_NOT_WALKFORWARD_SELECTION",
        "development_hash": market.dataset_hash,
        "development_cutoff": last_development_date.isoformat(),
        "plan_hash": plan_hash,
        "years": list(years),
        "periods": [p.__dict__ for p in slices],
        "cost_model": "academic-research-cost-v1",
        "out_of_sample_approved": False,
    })
    return HistoricalRobustnessReport(
        plan_hash=plan_hash,
        development_hash=market.dataset_hash,
        development_cutoff=last_development_date.isoformat(),
        periods=tuple(slices),
        report_hash=digest,
    )
