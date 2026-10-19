"""Prior completed-session OHLC levels, adapted from Shaakuni's MPL-2.0
Liquidity Levels & Order Blocks v1.4.0, © Shaakuni.

Derived component only; neither Pine visual parity nor full OB strategy port.
Source upload SHA-256: 54dabcd62a87df46e0b248ef290ccf3f1346d4b2f5f49ec72b6c68148e703f78
MPL-2.0: https://mozilla.org/MPL/2.0/
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CompletedLevels:
    previous_day_high: float | None
    previous_day_low: float | None
    previous_day_eq: float | None
    previous_week_high: float | None
    previous_week_low: float | None
    previous_week_eq: float | None


def completed_period_levels(
    bars: list[tuple[datetime, float, float]],
) -> list[CompletedLevels]:
    """Use only *completed* days and weeks; current bar never enters its own prior levels.

    Input timestamps must already be aligned to the source market's exchange date.
    Caller must supply chronological bars and must choose correct session boundaries.
    """
    if any(bars[i][0] >= bars[i + 1][0] for i in range(len(bars) - 1)):
        raise ValueError("bars must have strictly increasing timestamps")
    out: list[CompletedLevels] = []
    last_day = last_week = None
    day_hi = day_lo = week_hi = week_lo = None
    prior_day: tuple[float, float] | None = None
    prior_week: tuple[float, float] | None = None
    for ts, hi, lo in bars:
        if hi < lo:
            raise ValueError("high must be >= low")
        day_key = ts.date()
        week_key = (ts.isocalendar().year, ts.isocalendar().week)
        if last_day is not None and day_key != last_day:
            assert day_hi is not None and day_lo is not None
            prior_day = (day_hi, day_lo)
            day_hi = day_lo = None
        if last_week is not None and week_key != last_week:
            assert week_hi is not None and week_lo is not None
            prior_week = (week_hi, week_lo)
            week_hi = week_lo = None
        dh, dl = prior_day if prior_day is not None else (None, None)
        wh, wl = prior_week if prior_week is not None else (None, None)
        out.append(
            CompletedLevels(
                dh,
                dl,
                (dh + dl) / 2 if dh is not None and dl is not None else None,
                wh,
                wl,
                (wh + wl) / 2 if wh is not None and wl is not None else None,
            )
        )
        day_hi = hi if day_hi is None else max(day_hi, hi)
        day_lo = lo if day_lo is None else min(day_lo, lo)
        week_hi = hi if week_hi is None else max(week_hi, hi)
        week_lo = lo if week_lo is None else min(week_lo, lo)
        last_day, last_week = day_key, week_key
    return out
