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

    assert [item.timestamp.day for item in weekly] == [5]
    assert [item.value for item in weekly] == [5.0]
    assert weekly[0].available_at == _time(8)
    assert monthly == ()  # No February observation has closed January yet.


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


def test_weekly_resampling_is_prefix_stable_and_excludes_unfinished_week() -> None:
    from core.features.alignment import align_as_of

    observations = tuple(
        SeriesObservation("US20Y", _time(day), float(day))
        for day in (3, 5, 10, 12, 15)
    )
    assert resample_completed(observations[:2], TimeFrame.WEEK) == ()

    at_wednesday = resample_completed(observations[:3], TimeFrame.WEEK)
    at_next_monday = resample_completed(observations, TimeFrame.WEEK)
    assert [point.value for point in at_wednesday] == [5.0]
    assert [point.value for point in at_next_monday] == [5.0, 12.0]
    assert align_as_of((_time(5), _time(10)), at_wednesday) == (None, 5.0)
    assert align_as_of(
        (_time(5), _time(10), _time(12), _time(15)), at_next_monday
    ) == (None, 5.0, 5.0, 12.0)


def test_monthly_resampling_waits_for_a_new_month_and_publication() -> None:
    from core.features.alignment import align_as_of

    february = datetime(2024, 2, 1, 21, tzinfo=timezone.utc)
    february_2 = datetime(2024, 2, 2, 21, tzinfo=timezone.utc)
    february_3 = datetime(2024, 2, 3, 21, tzinfo=timezone.utc)
    observations = (
        SeriesObservation("US20Y", _time(30), 30.0),
        SeriesObservation("US20Y", _time(31), 31.0, february_3),
        SeriesObservation("US20Y", february, 40.0, february_2),
    )
    assert resample_completed(observations[:2], TimeFrame.MONTH) == ()

    closed = resample_completed(observations, TimeFrame.MONTH)
    assert len(closed) == 1
    assert closed[0].timestamp == _time(31)
    assert closed[0].available_at == february_3
    assert align_as_of((february, february_2, february_3), closed) == (
        None, None, 31.0
    )


def test_weekly_resampling_uses_iso_year_at_new_year() -> None:
    from core.features.alignment import align_as_of

    last_friday = datetime(2023, 12, 29, 21, tzinfo=timezone.utc)
    next_tuesday = datetime(2024, 1, 2, 21, tzinfo=timezone.utc)
    closed = resample_completed(
        (
            SeriesObservation("US20Y", last_friday, 23.0),
            SeriesObservation("US20Y", next_tuesday, 24.0),
        ),
        TimeFrame.WEEK,
    )
    assert [(point.timestamp, point.value) for point in closed] == [
        (last_friday, 23.0)
    ]
    assert align_as_of((last_friday, next_tuesday), closed) == (None, 23.0)


def test_weekly_closure_waits_through_missing_monday_and_next_release() -> None:
    from core.features.alignment import align_as_of

    friday = SeriesObservation("US20Y", _time(12), 12.0)
    next_tuesday = SeriesObservation("US20Y", _time(16), 16.0, _time(17))
    completed = resample_completed((friday, next_tuesday), TimeFrame.WEEK)

    assert len(completed) == 1
    assert completed[0].available_at == _time(17)
    assert align_as_of(
        (_time(12), _time(15), _time(16), _time(17)), completed
    ) == (None, None, None, 12.0)


def test_day_and_intraday_observations_keep_their_availability() -> None:
    source = (
        SeriesObservation("US20Y", _time(2), 2.0, _time(3)),
        SeriesObservation("US20Y", _time(3), 3.0),
    )
    for timeframe in (TimeFrame.DAY, TimeFrame.HOUR, TimeFrame.MINUTE):
        assert resample_completed(source, timeframe) == source
