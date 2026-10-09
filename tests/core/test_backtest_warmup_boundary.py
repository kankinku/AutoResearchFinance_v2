"""Warmup history can form indicators but must never authorize earlier orders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, MarketDataSet
from strategy_ir.schema import StrategyIR


def _fixture(*symbols: str) -> tuple[StrategyIR, MarketDataSet]:
    strategy = StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "warmup",
            "family": "test",
            "generation": 0,
            "indicators": {"ma": {"type": "SMA", "period": 3}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "ma", "value": 2}],
            },
            "exit": {"logic": "OR", "conditions": []},
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            symbol,
            close,
            close,
            close,
            close,
            100,
        )
        for symbol in symbols
        for index, close in enumerate((1, 2, 3, 4, 5, 6))
    )
    return strategy, MarketDataSet("warmup-v1", "development", bars)


@pytest.mark.parametrize("symbols", [("AAA",), ("AAA", "BBB")])
def test_signal_start_blocks_training_trades_but_keeps_indicator_history(
    symbols: tuple[str, ...],
) -> None:
    strategy, dataset = _fixture(*symbols)
    first_test = dataset.bars[4].timestamp
    result = BacktestEngine().run(
        BacktestRequest(
            "warmup-test", "unused", dataset, 1000, strategy=strategy, signal_start_at=first_test
        )
    )
    assert len(result.trades) == len(symbols)
    assert {trade.timestamp for trade in result.trades} == {dataset.bars[5].timestamp.isoformat()}
    assert all(trade.side == "buy" for trade in result.trades)
    assert result.equity_curve[0] == 1000
    assert result.equity_curve[3] == 1000


def test_signal_start_rejects_timezone_naive_datetime() -> None:
    strategy, dataset = _fixture("AAA")
    with pytest.raises(ValueError, match="timezone"):
        BacktestEngine().run(
            BacktestRequest(
                "warmup-bad",
                "unused",
                dataset,
                1000,
                strategy=strategy,
                signal_start_at=datetime(2024, 1, 5),
            )
        )
