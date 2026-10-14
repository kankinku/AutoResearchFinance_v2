"""Chronological train-only selection with non-overlapping *development* test windows.

Uses the unchanged canonical BacktestEngine and StrategyIR. Pretest bars
warm up signals but are never eligible to open positions in test replay.
This is NOT sealed OOS: original vendor data are latest-revision non-PIT.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Literal

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.market_audit import inspect_development_market_reference
from research.indicator_engine.strategy_adapter import (
    compile_research_hypothesis,
    evaluate_compiled_development,
)

_RESEARCH_COST = CostModel("academic-research-cost-v1", 1.0, 2.0, SlippageModel(5.0))
_ENTRIES = ("previous_range_breakout", "time_series_momentum")
_REGIME = "sma_direction"


@dataclass(frozen=True)
class ResearchForwardFold:
    train_end_index: int
    test_end_index: int
    train_cutoff: datetime
    test_start: datetime
    test_end: datetime
    selected_entry: str
    selected_hypothesis_hash: str
    training_choice_hash: str
    training_final_equities: tuple[tuple[str, float], ...]
    test_final_equity: float
    test_buyhold_price_only_equity: float
    trade_count: int
    first_trade_time: datetime | None
    test_equity_hash: str
    status: Literal["NON_PIT_DEVELOPMENT_FOLD"] = "NON_PIT_DEVELOPMENT_FOLD"


@dataclass(frozen=True)
class ResearchWalkForward:
    dataset_hash: str
    folds: tuple[ResearchForwardFold, ...]
    compounded_test_final_equity: float
    compounded_price_only_benchmark: float
    initial_cash: float
    report_hash: str
    status: Literal["NON_PIT_ROLLING_RESEARCH_ONLY"] = "NON_PIT_ROLLING_RESEARCH_ONLY"
    out_of_sample_approved: Literal[False] = False
    candidate_promotable: Literal[False] = False
    benchmark_independently_verified: Literal[False] = False
    point_in_time_verified: Literal[False] = False


def _prefix(market: MarketDataSet, end: int) -> MarketDataSet:
    return MarketDataSet(
        market.version, market.zone, market.bars[:end],
        market.timeframe, market.calendar, market.provenance,
    )


def run_development_walkforward(
    catalog: ResearchCatalog,
    market: MarketDataSet,
    *,
    train_bars: int = 756,
    test_bars: int = 252,
    min_final_test_bars: int = 100,
    initial_cash: float = 10_000.0,
) -> ResearchWalkForward:
    """Fit binary signal *choice* on prior prefix; trade only later windows.

    Entries are selected from a fixed pre-reviewed two-candidate set using
    previous window's canonical net-of-cost final equity. No optimization
    on any later test window. The testing capital resets each fold, with
    multiplication of returns for a comparable diagnostic stitched path.
    """
    if market.zone != DataZone.DEVELOPMENT:
        raise ResearchCatalogError("walkforward requires development data only")
    if market.timeframe != "1d" or market.calendar != "us_equities":
        raise ResearchCatalogError("walkforward expects daily US equity data")
    if len({bar.symbol for bar in market.bars}) != 1:
        raise ResearchCatalogError("walkforward currently single-symbol only")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ResearchCatalogError("invalid walkforward initial cash")
    if (
        not 300 <= train_bars <= 100_000
        or not 30 <= test_bars <= 10_000
        or not 30 <= min_final_test_bars <= test_bars
        or len(market.bars) < train_bars + min_final_test_bars
    ):
        raise ResearchCatalogError("insufficient data or invalid walkforward fold sizes")
    for name in (*_ENTRIES, _REGIME):
        if catalog.get_indicator(name).status != "VERIFIED":
            raise ResearchCatalogError("VERIFIED reviewed signals required")
    if tuple(bar.timestamp for bar in market.bars) != tuple(sorted(
        bar.timestamp for bar in market.bars
    )):
        raise ResearchCatalogError("walkforward requires ordered trading timestamps")

    folds: list[ResearchForwardFold] = []
    forward_equity = initial_cash
    benchmark_equity = initial_cash
    n = len(market.bars)
    for train_end in range(train_bars, n, test_bars):
        test_end = min(train_end + test_bars, n)
        if test_end - train_end < min_final_test_bars:
            break
        train_data = _prefix(market, train_end)
        training_scores: list[tuple[str, float]] = []
        choices = {}
        for name in _ENTRIES:
            possible = compose_hypotheses(catalog, signal_ids=(name, _REGIME))
            if len(possible) != 1:
                raise ResearchCatalogError("ambiguous research training composition")
            choices[name] = possible[0]
            compiled_train = compile_research_hypothesis(catalog, possible[0], train_data)
            scored = evaluate_compiled_development(
                compiled_train, train_data, initial_cash=initial_cash,
            )
            training_scores.append((name, scored.final_equity))
        # Stable lexicographic tie-breaker, never test-period-based.
        selected = sorted(training_scores, key=lambda row: (-row[1], row[0]))[0][0]
        choice_hash = content_hash({
            "version": "train-only-selection-v1",
            "train_data": train_data.dataset_hash,
            "cutoff": market.bars[train_end - 1].timestamp.isoformat(),
            "candidates": sorted(training_scores), "selected": selected,
        })
        run_data = _prefix(market, test_end)
        compiled = compile_research_hypothesis(catalog, choices[selected], run_data)
        start = market.bars[train_end].timestamp
        evaluated = BacktestEngine().run(BacktestRequest(
            run_id="academic-forward-" + choice_hash[:16],
            strategy_hash=compiled.strategy_hash, dataset=run_data,
            initial_cash=initial_cash, strategy=compiled.strategy,
            cost_model=_RESEARCH_COST, feature_values=compiled.feature_values,
            signal_start_at=start,
        ))
        if evaluated.exit_status != "SUCCEEDED":
            raise ResearchCatalogError("walkforward canonical backtest unsuccessful")
        if any(trade.timestamp < start.isoformat() for trade in evaluated.trades):
            raise ResearchCatalogError("pretest position leak in forward replay")
        if any(abs(item - initial_cash) > 1e-8
               for item in evaluated.equity_curve[:train_end + 1]):
            raise ResearchCatalogError("training PnL contaminated forward replay")
        ending = evaluated.equity_curve[-1]
        reference_bars = market.bars[train_end:test_end]
        reference = inspect_development_market_reference(MarketDataSet(
            market.version, DataZone.DEVELOPMENT, reference_bars,
            market.timeframe, market.calendar, market.provenance,
        ), initial_cash=initial_cash)
        benchmark = reference.price_only_marked_equity
        forward_equity *= ending / initial_cash
        benchmark_equity *= benchmark / initial_cash
        folds.append(ResearchForwardFold(
            train_end_index=train_end, test_end_index=test_end,
            train_cutoff=market.bars[train_end - 1].timestamp,
            test_start=start, test_end=market.bars[test_end - 1].timestamp,
            selected_entry=selected,
            selected_hypothesis_hash=choices[selected].identity_hash,
            training_choice_hash=choice_hash,
            training_final_equities=tuple(sorted(training_scores)),
            test_final_equity=ending, test_buyhold_price_only_equity=benchmark,
            trade_count=len(evaluated.trades),
            first_trade_time=(datetime.fromisoformat(evaluated.trades[0].timestamp)
                              if evaluated.trades else None),
            test_equity_hash=content_hash(evaluated.equity_curve[train_end:]),
        ))
    if not folds:
        raise ResearchCatalogError("no valid chronological walkforward fold")
    report_hash = content_hash({
        "version": "research-forward-test-v1", "dataset": market.dataset_hash,
        "train_bars": train_bars, "test_bars": test_bars,
        "minimum_test": min_final_test_bars, "initial_cash": initial_cash,
        "folds": [
            {"selection": fold.training_choice_hash, "test": fold.test_equity_hash,
             "start": fold.test_start.isoformat(), "end": fold.test_end.isoformat(),
             "selected": fold.selected_entry, "final": fold.test_final_equity}
            for fold in folds
        ],
        "benchmark": benchmark_equity, "compounded": forward_equity,
        "data_status": "NON_PIT_UNSEALED",
    })
    return ResearchWalkForward(
        dataset_hash=market.dataset_hash, folds=tuple(folds),
        compounded_test_final_equity=forward_equity,
        compounded_price_only_benchmark=benchmark_equity,
        initial_cash=initial_cash, report_hash=report_hash,
    )
