"""Academic research compilation boundary; no order execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Literal

from core.backtest.engine import BacktestEngine, BacktestRequest, Trade
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.bridge import ResearchSignalReplay, prepare_development_replay
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.models import ResearchHypothesis
from strategy_ir.schema import StrategyIR

_COST = CostModel("academic-research-cost-v1", 1.0, 2.0, SlippageModel(5.0))


@dataclass(frozen=True)
class CompiledAcademicStrategy:
    hypothesis_hash: str
    dataset_hash: str
    replay: ResearchSignalReplay
    strategy: StrategyIR
    strategy_hash: str
    feature_values: dict[str, tuple[float | None, ...]]
    status: Literal["DEVELOPMENT_ONLY"] = "DEVELOPMENT_ONLY"
    broker_executable: Literal[False] = False
    sealed_oos_approved: Literal[False] = False


@dataclass(frozen=True)
class AcademicDevelopmentResult:
    hypothesis_hash: str
    dataset_hash: str
    strategy_hash: str
    replay_hash: str
    equity_hash: str
    equity_curve: tuple[float, ...]
    initial_cash: float
    final_equity: float
    trades_count: int
    trades: tuple[Trade, ...]
    total_paid_costs: float
    status: Literal["NON_PIT_DEVELOPMENT_RESULT"] = "NON_PIT_DEVELOPMENT_RESULT"
    qqq_cagr_delta: None = None
    pbo: None = None
    dsr: None = None
    broker_executable: Literal[False] = False
    candidate_promotable: Literal[False] = False
    benchmark_verified: Literal[False] = False
    out_of_sample_approved: Literal[False] = False


def compile_research_hypothesis(
    catalog: ResearchCatalog,
    hypothesis: ResearchHypothesis,
    dataset: MarketDataSet,
) -> CompiledAcademicStrategy:
    """Compile two vetted binary features; block unreviewed risk overlay semantics."""
    replay = prepare_development_replay(catalog, hypothesis, dataset)
    if len(hypothesis.signal_ids) != 2 or hypothesis.roles != ("entry", "regime"):
        raise ResearchCatalogError("risk overlay requires a reviewed risk execution contract")
    entry, regime = hypothesis.signal_ids
    if (
        catalog.get_indicator(entry).calculator
        not in (
            "time_series_momentum",
            "previous_range_breakout",
        )
        or catalog.get_indicator(regime).calculator != "sma_direction"
    ):
        raise ResearchCatalogError("only reviewed boolean academic signals may compile")
    definitions_hash = content_hash(
        tuple(
            catalog.get_indicator(name).model_dump(mode="json", exclude={"status"})
            for name in hypothesis.signal_ids
        )
    )
    source_hash = content_hash(
        {
            "hypothesis": hypothesis.identity_hash,
            "definitions": definitions_hash,
            "replay": replay.replay_hash,
            "exit_policy": "exit_if_entry_signal_nonpositive",
            "cost_policy": _COST.version,
            "adapter_version": 1,
        }
    )
    # Canonical StrategyIR requires a native indicator. The dummy SMA has
    # no referenced conditions. Research decisions use only academic vectors.
    raw = {
        "schema_version": 1,
        "id": "academic_research_" + hypothesis.identity_hash[:16],
        "family": "academic_research",
        "generation": 0,
        "parents": [],
        "indicators": {"_unused_sma": {"type": "SMA", "period": 2}},
        "features": {
            name: {
                "feature_id": "academic.research." + name,
                "timeframe": "1d",
                "lag_bars": 0,
                "lookback": catalog.get_indicator(name).lookback,
            }
            for name in hypothesis.signal_ids
        },
        "entry": {
            "logic": "AND",
            "conditions": [{"op": "greater_than", "left": entry, "value": 0.5}],
        },
        "exit": {
            "logic": "OR",
            "conditions": [{"op": "less_equal", "left": entry, "value": 0.5}],
        },
        "regime_filters": [{"op": "greater_than", "left": regime, "value": 0.5}],
        "risk": {
            "stop_loss_pct": 0.0,
            "take_profit_pct": 0.0,
            "position_size_pct": 100.0,
        },
        "provenance": {
            "source_type": "academic-development-non-PIT",
            "source_path": "research.indicator_engine.strategy_adapter",
            "source_hash": source_hash,
        },
    }
    strategy = StrategyIR.model_validate(raw)
    strategy_hash = content_hash(strategy.model_dump(mode="json", by_alias=True))
    return CompiledAcademicStrategy(
        hypothesis_hash=hypothesis.identity_hash,
        dataset_hash=dataset.dataset_hash,
        replay=replay,
        strategy=strategy,
        strategy_hash=strategy_hash,
        feature_values=dict(replay.signals),
    )


def _raw_feature_inputs_for_core(
    strategy: StrategyIR,
    effective: dict[str, tuple[float | None, ...]],
) -> dict[str, tuple[float | None, ...]]:
    """Adapt research effective vectors to the core's one-time FeatureRef lag.

    Inherited research replay stores lag-applied, decision-time effective
    vectors. The protected backtester expects *raw* supplied series and
    applies StrategyIR.lag_bars itself. Reversing the already-applied prefix
    at this boundary prevents double lag without modifying either contract,
    hashes, or a single historical replay observation.
    """
    raw: dict[str, tuple[float | None, ...]] = {}
    if set(effective) != set(strategy.features):
        raise ResearchCatalogError("research replay feature aliases disagree with StrategyIR")
    for alias, series in effective.items():
        lag = strategy.features[alias].lag_bars
        if lag == 0:
            raw[alias] = series
            continue
        if lag >= len(series) or any(value is not None for value in series[:lag]):
            raise ResearchCatalogError("lagged research feature prefix is inconsistent")
        raw[alias] = series[lag:] + (None,) * lag
    return raw


def evaluate_compiled_development(
    compiled: CompiledAcademicStrategy,
    dataset: MarketDataSet,
    *,
    initial_cash: float = 10_000.0,
    signal_start_at: datetime | None = None,
) -> AcademicDevelopmentResult:
    """Costed local run; optional first signal is for forward-window warmups only.

    All previous bars may calculate indicators but cannot open positions.
    The caller must slice the equity curve at the forward start for metrics.
    """
    if DataZone(dataset.zone) is not DataZone.DEVELOPMENT:
        raise ResearchCatalogError("non-development market data is forbidden")
    if (
        dataset.dataset_hash != compiled.dataset_hash
        or dataset.dataset_hash != compiled.replay.data_hash
    ):
        raise ResearchCatalogError("data hash mismatch")
    actual_hash = content_hash(compiled.strategy.model_dump(mode="json", by_alias=True))
    if compiled.strategy_hash != actual_hash:
        raise ResearchCatalogError("strategy hash mismatch")
    if compiled.replay.hypothesis_hash != compiled.hypothesis_hash:
        raise ResearchCatalogError("hypothesis hash mismatch")
    if compiled.replay.timestamps != tuple(bar.timestamp for bar in dataset.bars):
        raise ResearchCatalogError("replay integrity: timestamp mismatch")
    expected_next = compiled.replay.timestamps[1:] + (None,)
    if compiled.replay.execution_not_before != expected_next:
        raise ResearchCatalogError("replay integrity: next-bar alignment mismatch")
    replay_body = {
        "hypothesis": compiled.replay.hypothesis_hash,
        "dataset": compiled.replay.data_hash,
        "signals": compiled.replay.signals,
        "decision_timestamps": [t.isoformat() for t in compiled.replay.timestamps],
        "earliest_next_bar": [t.isoformat() if t else None for t in expected_next],
        "research_only": True,
    }
    if content_hash(replay_body) != compiled.replay.replay_hash:
        raise ResearchCatalogError("replay integrity mismatch")
    if dict(compiled.replay.signals) != compiled.feature_values:
        raise ResearchCatalogError("precomputed feature mismatch")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ResearchCatalogError("initial cash must be positive finite")
    result = BacktestEngine().run(
        BacktestRequest(
            run_id="academic-development-" + compiled.strategy_hash[:16],
            strategy_hash=compiled.strategy_hash,
            dataset=dataset,
            initial_cash=initial_cash,
            strategy=compiled.strategy,
            cost_model=_COST,
            feature_values=_raw_feature_inputs_for_core(compiled.strategy, compiled.feature_values),
            signal_start_at=signal_start_at,
        )
    )
    if result.exit_status != "SUCCEEDED" or result.data_hash != compiled.dataset_hash:
        raise ResearchCatalogError("local canonical backtest failed integrity checks")
    return AcademicDevelopmentResult(
        hypothesis_hash=compiled.hypothesis_hash,
        dataset_hash=compiled.dataset_hash,
        strategy_hash=compiled.strategy_hash,
        replay_hash=compiled.replay.replay_hash,
        equity_hash=result.equity_curve_hash,
        equity_curve=result.equity_curve,
        initial_cash=initial_cash,
        final_equity=result.equity_curve[-1],
        trades_count=len(result.trades),
        trades=result.trades,
        total_paid_costs=sum(trade.cost for trade in result.trades),
    )
