from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from core.data.contracts import SeriesObservation
from core.features.time import to_utc


class TimeFrame(str, Enum):
    MINUTE = "1m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"
    MONTH = "1mo"


class SeriesRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    series_id: str = Field(min_length=1)
    field: str = Field(default="close", min_length=1)
    timeframe: TimeFrame = TimeFrame.DAY
    lag_bars: int = Field(default=0, ge=0)


class FeatureTransform(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    series: SeriesRef
    calculator: str = Field(min_length=1)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)

    def expression(self) -> str:
        parameters = ",".join(
            f"{key}={value}" for key, value in sorted(self.parameters.items())
        )
        return (
            f"{self.series.series_id}.{self.series.field}@{self.series.timeframe.value}:"
            f"{self.calculator}({parameters}):lag={self.series.lag_bars}"
        )


def resample_completed(
    observations: tuple[SeriesObservation, ...], timeframe: TimeFrame
) -> tuple[SeriesObservation, ...]:
    """Collapse observations to the last completed point in each calendar period."""

    ordered = tuple(sorted(observations, key=lambda item: to_utc(item.timestamp)))
    if not ordered:
        return ()
    series_ids = {item.series_id for item in ordered}
    if len(series_ids) != 1:
        raise ValueError("resampling requires one series_id")
    if timeframe in {
        TimeFrame.MINUTE,
        TimeFrame.FIVE_MINUTE,
        TimeFrame.FIFTEEN_MINUTE,
        TimeFrame.HOUR,
        TimeFrame.DAY,
    }:
        return ordered

    collapsed: list[SeriesObservation] = []
    current_key: tuple[int, int] | tuple[int, int, int] | None = None
    current: SeriesObservation | None = None
    for observation in ordered:
        timestamp = to_utc(observation.timestamp)
        key: tuple[int, int] | tuple[int, int, int]
        if timeframe is TimeFrame.WEEK:
            iso = timestamp.isocalendar()
            key = (iso.year, iso.week)
        else:
            key = (timestamp.year, timestamp.month)
        if current is not None and key != current_key:
            collapsed.append(current)
        current = observation
        current_key = key
    if current is not None:
        collapsed.append(current)
    return tuple(collapsed)
