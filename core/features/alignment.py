from __future__ import annotations

from bisect import bisect_right
from datetime import datetime

from core.data.contracts import SeriesObservation
from core.features.time import to_utc


def align_as_of(
    target_timestamps: tuple[datetime, ...],
    observations: tuple[SeriesObservation, ...],
) -> tuple[float | None, ...]:
    """Return the latest observation usable at every target timestamp.

    An observation is usable only when both its observation time and explicit
    availability time are no later than the target. Missing values remain None.
    """

    normalized_targets = tuple(to_utc(value) for value in target_timestamps)
    ordered = tuple(sorted(observations, key=lambda item: to_utc(item.timestamp)))
    timestamps = tuple(to_utc(item.timestamp) for item in ordered)
    result: list[float | None] = []
    for target in normalized_targets:
        position = bisect_right(timestamps, target) - 1
        value: float | None = None
        while position >= 0:
            observation = ordered[position]
            available_at = to_utc(observation.available_at or observation.timestamp)
            if available_at <= target:
                value = observation.value
                break
            position -= 1
        result.append(value)
    return tuple(result)
