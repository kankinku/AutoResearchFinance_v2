from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, MarketDataSet
from core.features.contracts import FeatureSpec
from strategy_ir.schema import Condition, IndicatorSpec
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
            _dataset((10, 9, 8, 9, 11, 10, 8, 7)),
            initial_cash=10_000,
            strategy=_strategy(),
        )
    )

    assert result.strategy_hash != "ignored-by-strategy-hash"
    assert len(result.trades) == 2
    assert result.trades[0].side == "buy"
    assert result.trades[1].side == "sell"
    assert result.trades[0].price == 10
    assert result.trades[1].price == 7
    assert result.equity_curve[-1] < result.equity_curve[0]


def test_strategy_backtest_executes_signal_on_next_bar_open() -> None:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            "TEST",
            open_price,
            max(open_price, close),
            min(open_price, close),
            close,
            1000,
        )
        for index, (open_price, close) in enumerate(((10, 20), (50, 60), (70, 80)))
    )
    strategy = _strategy().model_copy(deep=True)  # type: ignore[union-attr]
    strategy.entry.conditions = [Condition(op="greater_than", left="close", value=0)]
    strategy.exit.conditions = [Condition(op="greater_than", left="close", value=0)]

    result = BacktestEngine().run(
        BacktestRequest(
            "run-next-open",
            "hash",
            MarketDataSet("data-v1", "development", bars),
            1000,
            strategy=strategy,
        )
    )

    assert [(trade.side, trade.price) for trade in result.trades] == [
        ("buy", 50),
        ("sell", 70),
    ]


def test_strategy_backtest_handles_multiple_symbols_without_cross_symbol_bridging() -> None:
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            symbol,
            open_price,
            max(open_price, close),
            min(open_price, close),
            close,
            1000,
        )
        for symbol, prices in (
            ("AAA", ((10, 20), (50, 60), (70, 80))),
            ("BBB", ((100, 110), (150, 160), (170, 180))),
        )
        for index, (open_price, close) in enumerate(prices)
    )
    strategy = _strategy().model_copy(deep=True)  # type: ignore[union-attr]
    strategy.entry.conditions = [Condition(op="greater_than", left="close", value=0)]
    strategy.exit.conditions = [Condition(op="greater_than", left="close", value=0)]

    result = BacktestEngine().run(
        BacktestRequest(
            "run-multi-symbol",
            "hash",
            MarketDataSet("data-v1", "development", bars),
            1000,
            strategy=strategy,
        )
    )

    assert [(trade.symbol, trade.side, trade.price) for trade in result.trades] == [
        ("AAA", "buy", 50),
        ("BBB", "buy", 150),
        ("AAA", "sell", 70),
        ("BBB", "sell", 170),
    ]


def test_strategy_backtest_compares_price_reference_to_indicator_reference() -> None:
    strategy = _strategy().model_copy(deep=True)  # type: ignore[union-attr]
    strategy.entry.conditions = [Condition(op="greater_than", left="close", right="slow")]

    result = BacktestEngine().run(
        BacktestRequest(
            "run-reference-comparison",
            "hash",
            _dataset((10, 9, 8, 9, 11, 10)),
            1000,
            strategy=strategy,
        )
    )

    assert result.exit_status == "SUCCEEDED"


def test_strategy_backtest_rejects_unsupported_indicator() -> None:
    strategy = _strategy().model_copy(deep=True)  # type: ignore[union-attr]
    strategy.indicators["unknown"] = {"type": "NOT_REAL"}  # type: ignore[assignment]
    with pytest.raises(ValueError, match="unsupported indicator"):
        BacktestEngine().run(
            BacktestRequest("run-bad", "hash", _dataset((10, 11, 12)), 1000, strategy=strategy)
        )


def test_strategy_backtest_supports_extended_registered_indicator_calculators() -> None:
    strategy = _strategy().model_copy(deep=True)  # type: ignore[union-attr]
    strategy.indicators["macd"] = IndicatorSpec(
        type="MACD", period=3, parameters={"fast_period": 2, "slow_period": 3}
    )
    strategy.entry.conditions.append(
        Condition(op="greater_than", left="macd", value=-100)
    )

    result = BacktestEngine().run(
        BacktestRequest(
            "run-extended-indicator",
            "hash",
            _dataset((10, 11, 12, 13, 14)),
            1000,
            strategy=strategy,
        )
    )

    assert result.exit_status == "SUCCEEDED"


def test_strategy_backtest_uses_declared_external_feature_values() -> None:
    strategy = validate_strategy(
        {
            "schema_version": 1,
            "id": "feature-signal",
            "family": "macro",
            "generation": 0,
            "indicators": {"baseline": {"type": "SMA", "period": 2}},
            "features": {"vix": {"feature_id": "vix_percentile"}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "vix", "value": 0.8}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "less_than", "left": "vix", "value": 0.2}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )
    result = BacktestEngine().run(
        BacktestRequest(
            "run-feature",
            "hash",
            _dataset((10, 10, 10, 10)),
            1000,
            strategy=strategy,
                feature_values={"vix": (0.1, 0.9, 0.1, 0.1)},
        )
    )

    assert [trade.side for trade in result.trades] == ["buy", "sell"]


def test_strategy_backtest_applies_feature_reference_lag() -> None:
    strategy = validate_strategy(
        {
            "schema_version": 1,
            "id": "lagged-feature",
            "family": "macro",
            "generation": 0,
            "indicators": {"baseline": {"type": "SMA", "period": 2}},
            "features": {"vix": {"feature_id": "vix_percentile", "lag_bars": 1}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "vix", "value": 0.8}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "less_than", "left": "vix", "value": 0.2}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )
    result = BacktestEngine().run(
        BacktestRequest(
            "run-lagged-feature",
            "hash",
            _dataset((10, 10, 10, 10)),
            1000,
            strategy=strategy,
                feature_values={"vix": (0.1, 0.9, 0.1, 0.1)},
        )
    )

    assert [trade.side for trade in result.trades] == ["buy"]
    assert result.trades[0].timestamp.startswith("2024-01-04")


def test_strategy_backtest_rejects_missing_external_feature_values() -> None:
    strategy = _strategy().model_copy(deep=True)  # type: ignore[union-attr]
    strategy.features["vix"] = {"feature_id": "vix_percentile"}  # type: ignore[assignment]
    with pytest.raises(ValueError, match="missing feature values"):
        BacktestEngine().run(
            BacktestRequest(
                "run-missing-feature",
                "hash",
                _dataset((10, 11, 12)),
                1000,
                strategy=strategy,
            )
        )


def test_strategy_backtest_calculates_registered_feature_from_external_series() -> None:
    strategy = validate_strategy(
        {
            "schema_version": 1,
            "id": "calculated-feature",
            "family": "macro",
            "generation": 0,
            "indicators": {"baseline": {"type": "SMA", "period": 2}},
            "features": {"vix": {"feature_id": "vix_percentile"}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "vix", "value": 0.5}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "less_than", "left": "vix", "value": 0.6}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )
    feature_spec = FeatureSpec(
        name="vix_percentile",
        family="macro",
        inputs=("VIX.close",),
        calculator="percentile",
        lookback=2,
        formula="percentile(VIX.close, 2)",
        status="REGISTERED",
    )

    result = BacktestEngine().run(
        BacktestRequest(
            "run-calculated-feature",
            "hash",
            _dataset((10, 10, 10, 10)),
            1000,
            strategy=strategy,
            feature_specs={"vix_percentile": feature_spec},
                feature_inputs={"VIX.close": (10.0, 20.0, 5.0, 5.0)},
        )
    )

    assert [trade.side for trade in result.trades] == ["buy", "sell"]
