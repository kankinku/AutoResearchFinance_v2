from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, MarketDataSet
from strategy_ir.validator import validate_strategy


def _dataset(closes: tuple[float, ...]) -> MarketDataSet:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            "TEST",
            close,
            close,
            close,
            close,
            1000,
        )
        for index, close in enumerate(closes)
    )
    return MarketDataSet("data-v1", "development", bars)


def _strategy() -> object:
    return validate_strategy(
        {
            "schema_version": 1,
            "id": "signal-test",
            "family": "trend",
            "generation": 0,
            "indicators": {
                "fast": {"type": "SMA", "period": 2},
                "slow": {"type": "SMA", "period": 3},
            },
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "cross_above", "left": "fast", "right": "slow"}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "cross_below", "left": "fast", "right": "slow"}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )


def test_strategy_backtest_uses_ir_signals_and_reports_trades() -> None:
    result = BacktestEngine().run(
        BacktestRequest(
            "run-signal",
            "ignored-by-strategy-hash",
            _dataset((10, 9, 8, 9, 11, 10, 8)),
            initial_cash=10_000,
            strategy=_strategy(),
        )
    )

    assert result.strategy_hash != "ignored-by-strategy-hash"
    assert len(result.trades) == 2
    assert result.trades[0].side == "buy"
    assert result.trades[1].side == "sell"
    assert result.equity_curve[-1] < result.equity_curve[0]


def test_strategy_backtest_rejects_unsupported_indicator() -> None:
    strategy = _strategy().model_copy(deep=True)  # type: ignore[union-attr]
    strategy.indicators["unknown"] = {"type": "NOT_REAL"}  # type: ignore[assignment]
    with pytest.raises(ValueError, match="unsupported indicator"):
        BacktestEngine().run(
            BacktestRequest("run-bad", "hash", _dataset((10, 11, 12)), 1000, strategy=strategy)
        )
