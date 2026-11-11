from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, DataZone, MarketDataSet, SeriesDataSet, SeriesObservation
from core.features.contracts import FeatureSpec
from strategy_ir.schema import StrategyIR


def _bar(day: int, close: float) -> Bar:
    timestamp = datetime(2024, 1, day, 21, tzinfo=timezone.utc)
    return Bar(timestamp, "AAPL", close - 0.5, close + 1.0, close - 1.0, close, 100.0)


def _strategy() -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "weekly-series",
            "family": "macro",
            "generation": 0,
            "indicators": {"baseline": {"type": "SMA", "period": 2}},
            "features": {"macro_rsi": {"feature_id": "weekly_rsi", "timeframe": "1w"}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "macro_rsi", "value": 0}],
            },
            "exit": {"logic": "AND", "conditions": []},
            "risk": {"stop_loss_pct": 0.0, "take_profit_pct": 0.0},
        }
    )


def _feature_spec() -> FeatureSpec:
    return FeatureSpec(
        name="weekly_rsi",
        family="momentum",
        inputs=("US10Y.close",),
        calculator="rsi",
        timeframe="1w",
        lookback=2,
        formula="rsi(US10Y.close, 2)",
        status="REGISTERED",
    )


def test_backtest_can_calculate_weekly_rsi_from_us10y_as_of_close() -> None:
    # Three completed weeks provide enough data for RSI warmup. The current
    # last week remains provisional until the following Monday is published.
    bars = tuple(_bar(day, float(day + 10)) for day in range(1, 30))
    observations = tuple(
        SeriesObservation("US10Y", bars[index].timestamp, float(index + 1))
        for index in (4, 11, 18, 25, 28)
    )
    request = BacktestRequest(
        run_id="weekly-series-run",
        strategy_hash="unhashed",
        dataset=MarketDataSet("bars-v1", DataZone.DEVELOPMENT, bars),
        initial_cash=1000.0,
        strategy=_strategy(),
        feature_specs={"weekly_rsi": _feature_spec()},
        external_series=SeriesDataSet("rates-v1", DataZone.DEVELOPMENT, observations),
    )

    result = BacktestEngine().run(request)

    assert result.exit_status == "SUCCEEDED"
    assert any(trade.side == "buy" for trade in result.trades)


def test_unavailable_future_external_observation_is_not_used() -> None:
    bars = tuple(_bar(day, float(day + 10)) for day in range(1, 11))
    late = SeriesObservation(
        "US10Y", bars[9].timestamp, 20.0, bars[9].timestamp + timedelta(days=2)
    )
    request = BacktestRequest(
        run_id="late-series-run",
        strategy_hash="unhashed",
        dataset=MarketDataSet("bars-v1", DataZone.DEVELOPMENT, bars),
        initial_cash=1000.0,
        strategy=_strategy(),
        feature_specs={"weekly_rsi": _feature_spec()},
        external_series=SeriesDataSet("rates-v1", DataZone.DEVELOPMENT, (late,)),
    )

    result = BacktestEngine().run(request)

    assert not result.trades


def test_feature_reference_can_select_source_series_and_lookback() -> None:
    bars = tuple(_bar(day, float(day + 10)) for day in range(1, 11))
    strategy_data = _strategy().model_dump()
    strategy_data["features"] = {
        "macro_rsi": {
            "feature_id": "weekly_rsi",
            "inputs": ("US10Y.close",),
            "timeframe": "1w",
            "lookback": 3,
        }
    }
    strategy = StrategyIR.model_validate(strategy_data)
    spec = _feature_spec().model_copy(update={"inputs": ("MACRO.close",)})
    observations = tuple(
        SeriesObservation("US10Y", bars[index].timestamp, float(index + 1))
        for index in range(len(bars))
    )

    result = BacktestEngine().run(
        BacktestRequest(
            run_id="selected-series-run",
            strategy_hash="unhashed",
            dataset=MarketDataSet("bars-v1", DataZone.DEVELOPMENT, bars),
            initial_cash=1000.0,
            strategy=strategy,
            feature_specs={"weekly_rsi": spec},
            external_series=SeriesDataSet("rates-v1", DataZone.DEVELOPMENT, observations),
        )
    )

    assert result.exit_status == "SUCCEEDED"


def test_weekly_external_macro_signal_trades_only_after_period_closes() -> None:
    from strategy_ir.schema import Condition, FeatureRef

    # January 15 is a missing observation (holiday); closure must wait
    # for the following week's first reported bar, January 16.
    bars = tuple(_bar(day, float(day + 10)) for day in range(1, 18) if day != 15)
    market = MarketDataSet("week-close-gate", DataZone.DEVELOPMENT, bars)
    source = SeriesDataSet(
        "weekly-inputs",
        DataZone.DEVELOPMENT,
        tuple(
            SeriesObservation("US10Y", _bar(day, float(day + 10)).timestamp, value)
            for day, value in ((5, 1.0), (10, 100.0), (12, 100.0), (16, 1.0))
        ),
    )
    strategy = _strategy().model_copy(deep=True)
    strategy.features = {"macro_rsi": FeatureRef(feature_id="weekly_sma", timeframe="1w")}
    strategy.entry.conditions = [
        Condition(op="greater_than", left="macro_rsi", value=50),
    ]
    strategy.exit.conditions = []
    spec = FeatureSpec(
        name="weekly_sma",
        family="macro",
        inputs=("US10Y.close",),
        calculator="sma",
        timeframe="1w",
        lookback=1,
        formula="sma(US10Y.close, 1)",
        status="REGISTERED",
    )

    result = BacktestEngine().run(
        BacktestRequest(
            run_id="weekly-no-partial-leak",
            strategy_hash="not-hashed",
            dataset=market,
            initial_cash=1000.0,
            strategy=strategy,
            feature_specs={"weekly_sma": spec},
            external_series=source,
        )
    )

    assert [trade.side for trade in result.trades] == ["buy"]
    assert result.trades[0].timestamp == bars[-1].timestamp.isoformat()
