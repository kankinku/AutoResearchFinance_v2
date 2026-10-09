"""Time-weighted invested-capital exposure must not be inferred from trade counts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import Trade
from core.data.contracts import Bar, MarketDataSet
from experiments.candidate_generator import Candidate
from orchestration.pipeline import GenerationPipeline, _capital_exposure
from strategy_ir.schema import StrategyIR


def _dataset(*symbols: str, length: int = 4) -> MarketDataSet:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            name,
            100,
            100,
            100,
            100,
            10_000,
        )
        for name in symbols
        for i in range(length)
    )
    return MarketDataSet("exposure-v1", "development", bars)


def _strategy() -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "exposure-fixture",
            "family": "fixture",
            "generation": 0,
            "indicators": {"ma": {"type": "SMA", "period": 1}},
            "entry": {"logic": "AND", "conditions": [
                {"op": "greater_than", "left": "close", "value": 0}
            ]},
            "exit": {"logic": "AND", "conditions": [
                {"op": "greater_than", "left": "close", "value": 0}
            ]},
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )


def test_exposure_tracks_fraction_of_capital_held_at_each_close() -> None:
    data = _dataset("AAA")
    trade_day1 = data.bars[1].timestamp.isoformat()
    trade_day3 = data.bars[3].timestamp.isoformat()
    trades = (
        Trade(trade_day1, "buy", 100, 10, 1000, 0, "AAA"),
        Trade(trade_day3, "sell", 100, 10, 1000, 0, "AAA"),
    )
    # Positions are held at 2 of 4 bar closes, not 1 of 4 closed trades.
    assert _capital_exposure(data, (1000,) * 4, trades) == pytest.approx(0.5)
    assert _capital_exposure(data, (1000,) * 4, ()) == 0


def test_exposure_tracks_multi_symbol_capital_proportions() -> None:
    data = _dataset("AAA", "BBB")
    first = data.bars[1].timestamp.isoformat()
    last = data.bars[3].timestamp.isoformat()
    trades = (
        Trade(first, "buy", 100, 5, 500, 0, "AAA"),
        Trade(first, "buy", 100, 5, 500, 0, "BBB"),
        Trade(last, "sell", 100, 5, 500, 0, "AAA"),
    )
    # 0%, 100%, 100%, 50% gross market-value exposure.
    assert _capital_exposure(data, (1000,) * 4, trades) == pytest.approx(0.625)


def test_pipeline_metrics_use_actual_capital_exposure() -> None:
    strategy = _strategy()
    candidate = Candidate(strategy, {}, (), strategy.strategy_id, "candidate-exposure")
    metrics, trades, _ = GenerationPipeline()._evaluate(candidate, _dataset("AAA"), "full")

    assert [trade.side for trade in trades] == ["buy", "sell", "buy"]
    assert metrics.trade_count == 1
    assert metrics.exposure == pytest.approx(0.5)
