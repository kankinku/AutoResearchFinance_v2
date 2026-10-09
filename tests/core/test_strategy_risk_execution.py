"""Executable semantics for declared regime filters and trailing exits.

Signals are decided on completed closes, and orders fill on the next open;
trailing peaks are symbol-local and reset on every new entry.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, MarketDataSet
from strategy_ir.schema import Condition, StrategyIR


def _strategy(*, trailing_pct: float | None = None) -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "risk-gate",
            "family": "test",
            "generation": 0,
            "indicators": {"ma": {"type": "SMA", "period": 1}},
            "entry": {"logic": "AND", "conditions": [
                {"op": "greater_than", "left": "close", "value": 0},
            ]},
            "exit": {"logic": "OR", "conditions": []},
            "risk": {
                "stop_loss_pct": 0,
                "take_profit_pct": 0,
                "trailing_stop_pct": trailing_pct,
            },
        }
    )


def _data(*series: tuple[str, tuple[float, ...]]) -> MarketDataSet:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            name,
            price,
            price,
            price,
            price,
            1000,
        )
        for name, closes in series
        for i, price in enumerate(closes)
    )
    return MarketDataSet("risk-data-v1", "development", bars)


def _run(strategy: StrategyIR, data: MarketDataSet):
    return BacktestEngine().run(BacktestRequest("risk-case", "unused", data, 1000, strategy))


def test_single_symbol_trailing_stop_exits_on_next_open_after_drawdown() -> None:
    strategy = _strategy(trailing_pct=10.0)
    data = _data(("AAA", (100, 100, 120, 108, 108)))
    result = _run(strategy, data)

    assert [(trade.side, trade.price) for trade in result.trades] == [
        ("buy", 100),
        ("sell", 108),
    ]
    assert result.trades[1].timestamp == data.bars[4].timestamp.isoformat()


def test_zero_trailing_stop_is_disabled() -> None:
    result = _run(_strategy(trailing_pct=0), _data(("AAA", (100, 100, 120, 108, 108))))
    assert [trade.side for trade in result.trades] == ["buy"]


def test_multi_symbol_trailing_stop_keeps_independent_peaks() -> None:
    result = _run(
        _strategy(trailing_pct=10),
        _data(
            ("AAA", (100, 100, 120, 108, 108)),
            ("BBB", (100, 100, 130, 110, 110)),
        ),
    )
    assert [(trade.symbol, trade.side, trade.price) for trade in result.trades] == [
        ("AAA", "buy", 100),
        ("BBB", "buy", 100),
        ("AAA", "sell", 108),
        ("BBB", "sell", 110),
    ]


def test_regime_filters_delay_entry_until_signal_allowed() -> None:
    strategy = _strategy()
    strategy.regime_filters = [Condition(op="greater_equal", left="close", value=7)]
    result = _run(strategy, _data(("AAA", (5, 6, 7, 8, 9))))
    assert [(trade.side, trade.price) for trade in result.trades] == [("buy", 8)]


def test_multi_symbol_regime_filters_only_gate_matching_symbol() -> None:
    strategy = _strategy()
    strategy.regime_filters = [Condition(op="less_than", left="close", value=15)]
    result = _run(
        strategy,
        _data(("AAA", (5, 6, 7)), ("BBB", (20, 21, 22))),
    )
    assert [(trade.symbol, trade.side) for trade in result.trades] == [("AAA", "buy")]


def test_regime_does_not_cancel_normal_exit_after_entry() -> None:
    strategy = _strategy()
    strategy.regime_filters = [Condition(op="less_than", left="close", value=15)]
    strategy.exit.conditions = [Condition(op="greater_than", left="close", value=15)]
    result = _run(strategy, _data(("AAA", (10, 14, 16, 17))))
    assert [(trade.side, trade.price) for trade in result.trades] == [
        ("buy", 14),
        ("sell", 17),
    ]


def test_trailing_peak_resets_after_exit_and_reentry() -> None:
    strategy = _strategy(trailing_pct=10)
    result = _run(
        strategy,
        _data(("AAA", (100, 100, 120, 108, 108, 100, 91, 91))),
    )
    # First entry peaks at 120 and exits after 108; second peaks only at 100.
    # The 91 close is a 9% second-position drawdown and must not exit.
    assert [trade.side for trade in result.trades] == ["buy", "sell", "buy"]


def test_disabled_regime_filters_do_not_gate_entries() -> None:
    strategy = _strategy()
    strategy.regime_filters = [
        Condition(op="less_than", left="close", value=0, enabled=False),
    ]
    result = _run(strategy, _data(("AAA", (10, 11, 12))))
    assert [(trade.side, trade.price) for trade in result.trades] == [("buy", 11)]
