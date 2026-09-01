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
    bars = tuple(_bar(day, float(day + 10)) for day in range(1, 11))
    observations = tuple(
        SeriesObservation("US10Y", bars[index].timestamp, float(index + 1)) for index in (4, 9)
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
