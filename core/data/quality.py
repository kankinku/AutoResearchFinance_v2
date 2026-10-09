"""Point-in-time declaration assessment; never certifies historical vendor accuracy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.data.contracts import MarketDataSet


@dataclass(frozen=True)
class MarketDataQuality:
    status: str
    issues: tuple[str, ...]
    point_in_time_verified: bool = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "issues": list(self.issues),
            "point_in_time_verified": self.point_in_time_verified,
        }


def market_data_quality(dataset: MarketDataSet) -> MarketDataQuality:
    """Report source declarations without promoting unverified data to validated OOS."""
    issues: list[str] = []
    provenance = dataset.provenance
    if not dataset.bars:
        issues.append("empty_market_data")
    if dataset.calendar == "continuous" and _has_continuous_gaps(dataset):
        issues.append("missing_continuous_bars")
    if provenance is None:
        issues.append("provenance_missing")
    else:
        if provenance.revision_policy != "as_of":
            issues.append("revisions_not_as_of")
        if provenance.universe_policy == "current_constituents":
            issues.append("survivorship_risk")
        if provenance.universe_policy != "single_symbol" and not provenance.includes_delisted:
            issues.append("delisted_assets_missing")
        if provenance.corporate_action_policy == "raw" or not provenance.corporate_action_reference:
            issues.append("corporate_action_adjustment_unverified")
    return MarketDataQuality("UNVERIFIED" if issues else "DECLARED_POINT_IN_TIME", tuple(issues))


def _has_continuous_gaps(dataset: MarketDataSet) -> bool:
    """Detect gaps only where a 24/7 cadence is a legitimate assumption.

    Exchange calendars require actual session/holiday data and are not inferred.
    A 50% time tolerance avoids classifying normal daily timezone/DST drift
    as one missing day. Monthly bars lack a fixed duration.
    """
    intervals = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1),
        "1w": timedelta(weeks=1),
    }
    expected = intervals.get(dataset.timeframe)
    if expected is None:
        return False
    previous_by_symbol: dict[str, datetime] = {}
    for bar in dataset.bars:
        previous = previous_by_symbol.get(bar.symbol)
        if previous is not None and bar.timestamp - previous > expected * 1.5:
            return True
        previous_by_symbol[bar.symbol] = bar.timestamp
    return False
