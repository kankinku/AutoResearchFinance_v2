from __future__ import annotations

from datetime import datetime, timezone

from core.data.contracts import SeriesObservation
from core.features.contracts import FeatureSpec
from core.features.series import FeatureTransform, SeriesRef, TimeFrame, resample_completed
from strategy_ir.schema import FeatureRef


def _time(day: int) -> datetime:
    return datetime(2024, 1, day, 21, tzinfo=timezone.utc)


def test_series_ref_supports_weekly_and_monthly_external_transforms() -> None:
    ref = SeriesRef(series_id="US20Y", field="close", timeframe=TimeFrame.WEEK, lag_bars=1)
    transform = FeatureTransform(series=ref, calculator="rsi", parameters={"period": 14})

    assert transform.expression() == "US20Y.close@1w:rsi(period=14):lag=1"


def test_completed_resampling_emits_last_observation_of_each_period() -> None:
    observations = tuple(
        SeriesObservation("US20Y", _time(day), float(day)) for day in (1, 2, 3, 4, 5, 8)
    )

    weekly = resample_completed(observations, TimeFrame.WEEK)
    monthly = resample_completed(observations, TimeFrame.MONTH)

    assert [item.timestamp.day for item in weekly] == [5, 8]
    assert [item.value for item in weekly] == [5.0, 8.0]
    assert [item.timestamp.day for item in monthly] == [8]
    assert monthly[0].value == 8.0


def test_feature_contracts_accept_weekly_monthly_and_strategy_refs() -> None:
    weekly = FeatureSpec(
        name="weekly_rsi",
        family="momentum",
        inputs=("US20Y.close",),
        timeframe="1w",
        lookback=14,
        formula="rsi(US20Y.close, 14)",
    )
    monthly = FeatureRef(feature_id="monthly_macd", timeframe="1mo")

    assert weekly.timeframe == "1w"
    assert monthly.timeframe == "1mo"
