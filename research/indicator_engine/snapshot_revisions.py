"""Development-only observations of revisions across two collected vendor files.

Vendor retrieval timestamps are *asserted metadata*, not independently signed
publication proof. This detects measurable historical revisions after a future
re-download; it never reconstructs what a trader actually saw years ago.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash

FIELDS = ("open", "high", "low", "close", "volume")
SnapshotStatus = Literal[
    "NO_OVERLAPPING_SESSIONS",
    "INCOMPARABLE_SNAPSHOTS",
    "UNORDERED_SNAPSHOT_TIMES",
    "HISTORICAL_ROWS_REVISED",
    "OVERLAPPING_ROWS_UNCHANGED",
]


@dataclass(frozen=True)
class PriceSnapshotRevisionReport:
    status: SnapshotStatus
    earlier_dataset_hash: str
    later_dataset_hash: str
    earlier_collected_at: str | None
    later_collected_at: str | None
    comparable_bars: int
    changed_bars: int
    changed_date_examples: tuple[str, ...]
    maximum_relative_difference: float
    comparison_hash: str
    independence: Literal["SAME_VENDOR_DECLARED_SNAPSHOT_TIMES"] = (
        "SAME_VENDOR_DECLARED_SNAPSHOT_TIMES"
    )
    historical_point_in_time_price_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "earlier_dataset_hash": self.earlier_dataset_hash,
            "later_dataset_hash": self.later_dataset_hash,
            "earlier_collected_at": self.earlier_collected_at,
            "later_collected_at": self.later_collected_at,
            "comparable_bars": self.comparable_bars,
            "changed_bars": self.changed_bars,
            "changed_date_examples": list(self.changed_date_examples),
            "maximum_relative_difference": self.maximum_relative_difference,
            "comparison_hash": self.comparison_hash,
            "independence": self.independence,
            "historical_point_in_time_price_verified": False,
            "broker_executable": False,
        }


def compare_collected_market_snapshots(
    earlier: MarketDataSet,
    later: MarketDataSet,
    *,
    tolerance_relative: float = 1e-8,
) -> PriceSnapshotRevisionReport:
    """Pair historical OHLCV bars, rejecting policy/vendor/period conflation."""
    if not isfinite(tolerance_relative) or tolerance_relative < 0:
        raise ValueError("revision comparison tolerance must be finite nonnegative")
    a, b = earlier.provenance, later.provenance
    old_time = a.retrieved_at.isoformat() if a else None
    new_time = b.retrieved_at.isoformat() if b else None
    valid = (
        earlier.zone is DataZone.DEVELOPMENT
        and later.zone is DataZone.DEVELOPMENT
        and earlier.calendar == later.calendar == "us_equities"
        and earlier.timeframe == later.timeframe == "1d"
        and a is not None and b is not None
        and a.source_id == b.source_id
        and a.corporate_action_policy == b.corporate_action_policy
        and {bar.symbol for bar in earlier.bars} ==
            {bar.symbol for bar in later.bars}
        and len({bar.symbol for bar in earlier.bars}) == 1
    )
    old_by = {(x.symbol, x.timestamp): x for x in earlier.bars}
    new_by = {(x.symbol, x.timestamp): x for x in later.bars}
    common = sorted(old_by.keys() & new_by.keys())
    dates: list[str] = []
    max_difference = 0.0
    status: SnapshotStatus
    if not valid:
        status = "INCOMPARABLE_SNAPSHOTS"
    elif a is not None and b is not None and a.retrieved_at >= b.retrieved_at:
        status = "UNORDERED_SNAPSHOT_TIMES"
    elif not common:
        status = "NO_OVERLAPPING_SESSIONS"
    else:
        for key in common:
            old, new = old_by[key], new_by[key]
            changed = False
            for field in FIELDS:
                x = float(getattr(old, field))
                y = float(getattr(new, field))
                magnitude = abs(x-y) / max(abs(x), abs(y), 1e-12)
                max_difference = max(max_difference, magnitude)
                if magnitude > tolerance_relative:
                    changed = True
            if changed:
                dates.append(key[1].date().isoformat())
        status = "HISTORICAL_ROWS_REVISED" if dates else "OVERLAPPING_ROWS_UNCHANGED"
    if status in {"INCOMPARABLE_SNAPSHOTS", "UNORDERED_SNAPSHOT_TIMES"}:
        common = []
    proof = {
        "schema": "revisions-observed-v1",
        "earlier": earlier.dataset_hash,
        "later": later.dataset_hash,
        "old_collected": old_time,
        "new_collected": new_time,
        "status": status,
        "overlap": len(common),
        "changed_dates": dates,
        "max_relative_difference": max_difference,
        "threshold": tolerance_relative,
    }
    return PriceSnapshotRevisionReport(
        status=status,
        earlier_dataset_hash=earlier.dataset_hash,
        later_dataset_hash=later.dataset_hash,
        earlier_collected_at=old_time,
        later_collected_at=new_time,
        comparable_bars=len(common),
        changed_bars=len(dates),
        changed_date_examples=tuple(dates[:20]),
        maximum_relative_difference=max_difference,
        comparison_hash=content_hash(proof),
    )
