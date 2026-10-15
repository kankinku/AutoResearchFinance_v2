"""Pinned NYSE published closure dates, distinct from market-price provenance.

Curated from four dated NYSE/ICE public statements, including the 2025-01-09
unscheduled presidential mourning closure.  This detects gaps between published
regular sessions; it is NOT historical PIT price or corporate-action evidence.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from core.data.contracts import MarketDataSet

_FILENAME = Path(__file__).with_name("nyse_public_closures_2020_2026_v1.json")
_EXPECTED_SHA = "1a43f51dd026d0ca46ec48c3752d8fe58996d1e8972ae542f28007ae8d2a8f9a"
_FIRST = date(2020, 1, 1)
_LAST = date(2026, 12, 31)
_MAX_DETAILS = 30

CalendarStatus = Literal[
    "MATCHED_PINNED_NYSE_PUBLIC_SCHEDULE",
    "MISMATCH_PINNED_NYSE_PUBLIC_SCHEDULE",
    "OUTSIDE_PINNED_YEARS",
    "UNSUPPORTED_SESSION_LABELS",
    "UNSUPPORTED_MARKET_DATA",
]


@dataclass(frozen=True)
class PublishedNYSECalendarAudit:
    status: CalendarStatus
    source_sha256: str
    reference_years: tuple[int, ...]
    comparison_start: str | None
    comparison_end: str | None
    expected_sessions: int
    observed_sessions: int
    missing_count: int
    unexpected_count: int
    missing_sessions: tuple[str, ...]
    unexpected_sessions: tuple[str, ...]
    comparison_scope: str
    regular_session_schedule_matched: bool = False
    point_in_time_price_verified: bool = False
    corporate_actions_verified: bool = False
    broker_executable: bool = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "calendar_source_sha256": self.source_sha256,
            "reference_years": list(self.reference_years),
            "comparison_start": self.comparison_start,
            "comparison_end": self.comparison_end,
            "expected_sessions": self.expected_sessions,
            "observed_sessions": self.observed_sessions,
            "missing_count": self.missing_count,
            "unexpected_count": self.unexpected_count,
            "missing_session_examples": list(self.missing_sessions),
            "unexpected_session_examples": list(self.unexpected_sessions),
            "comparison_scope": self.comparison_scope,
            "regular_session_schedule_matched": self.regular_session_schedule_matched,
            "calendar_reference_is_exchange_public_notice": True,
            "independent_historical_price_pit_verified": False,
            "corporate_actions_verified": False,
            "broker_executable": False,
        }


def _closed_dates() -> frozenset[date]:
    data = _FILENAME.read_bytes()
    if hashlib.sha256(data).hexdigest() != _EXPECTED_SHA:
        raise ValueError("pinned NYSE exchange calendar reference integrity mismatch")
    payload = json.loads(data)
    if payload.get("schema") != "curated_nyse_public_closures_v1":
        raise ValueError("wrong published exchange-calendar schema")
    if payload.get("covered_years") != list(range(2020, 2027)):
        raise ValueError("unsupported exchange-calendar reference years")
    raw = payload["closed_sessions_by_year"]
    if set(raw) != {str(y) for y in range(2020, 2027)}:
        raise ValueError("calendar year keys have changed")
    rows: list[date] = []
    for key in sorted(raw):
        dates = raw[key]
        if not isinstance(dates, list) or not 8 <= len(dates) <= 12:
            raise ValueError("unexpected NYSE annual holiday count")
        for item in dates:
            if not isinstance(item, str):
                raise ValueError("invalid holiday date")
            stamp = date.fromisoformat(item)
            if stamp.year != int(key) or stamp.weekday() >= 5:
                raise ValueError("invalid exchange closed date")
            rows.append(stamp)
    if len(rows) != len(set(rows)):
        raise ValueError("duplicate NYSE holiday")
    if date(2025, 1, 9) not in rows or date(2022, 6, 20) not in rows:
        raise ValueError("missing mandatory extraordinary or Juneteenth closure")
    return frozenset(rows)


def verify_published_nyse_regular_sessions(
    market: MarketDataSet,
    *,
    requested_start: date | None = None,
    requested_end: date | None = None,
) -> PublishedNYSECalendarAudit:
    """Compare an EOD time series to the locally pinned official NYSE releases.

    Comparison covers requested file dates, if provided, or observed first-last
    dates. Source notices document scheduled full-day market closures plus one
    special event and are a bounded, hand-curated exchange-session reference.
    No external price feed, broker, or calendar API is called at runtime.
    """
    closures = _closed_dates()  # Fail closed on tampered reference before returning a status.

    def _result(
        status: CalendarStatus, start: date | None, end: date | None,
        expected: int = 0, observed: int = 0,
        missing: tuple[date, ...] = (), unexpected: tuple[date, ...] = (),
    ) -> PublishedNYSECalendarAudit:
        return PublishedNYSECalendarAudit(
            status=status,
            source_sha256=_EXPECTED_SHA,
            reference_years=tuple(range(2020, 2027)),
            comparison_start=start.isoformat() if start else None,
            comparison_end=end.isoformat() if end else None,
            expected_sessions=expected,
            observed_sessions=observed,
            missing_count=len(missing),
            unexpected_count=len(unexpected),
            missing_sessions=tuple(x.isoformat() for x in missing[:_MAX_DETAILS]),
            unexpected_sessions=tuple(x.isoformat() for x in unexpected[:_MAX_DETAILS]),
            comparison_scope=(
                "requested_file_bounds" if requested_start is not None
                else "observed_first_to_last_only"
            ),
            regular_session_schedule_matched=(
                status == "MATCHED_PINNED_NYSE_PUBLIC_SCHEDULE"
            ),
        )

    if (
        market.calendar != "us_equities" or market.timeframe != "1d"
        or not market.bars or len({b.symbol for b in market.bars}) != 1
        or (requested_start is None) != (requested_end is None)
    ):
        return _result("UNSUPPORTED_MARKET_DATA", None, None)
    seen_days = tuple(bar.timestamp.date() for bar in market.bars)
    # Tiingo/KIS daily feeds have midnight UTC as the trading-session label.
    # Non-midnight or non-UTC timestamps require an explicit exchange time-zone
    # mapping; never implicitly label them by UTC calendar day.
    if any(
        bar.timestamp.utcoffset() != timedelta(0)
        or bar.timestamp.time() != datetime.min.time()
        for bar in market.bars
    ):
        return _result("UNSUPPORTED_SESSION_LABELS", min(seen_days), max(seen_days))
    begin = requested_start if requested_start is not None else min(seen_days)
    end = requested_end if requested_end is not None else max(seen_days)
    if begin > end:
        return _result("UNSUPPORTED_MARKET_DATA", begin, end)
    if begin < _FIRST or end > _LAST:
        return _result("OUTSIDE_PINNED_YEARS", begin, end)

    expected: set[date] = set()
    cursor = begin
    while cursor <= end:
        if cursor.weekday() < 5 and cursor not in closures:
            expected.add(cursor)
        cursor += timedelta(days=1)
    observed = set(seen_days)
    missing = tuple(sorted(expected - observed))
    unexpected = tuple(sorted(observed - expected))
    # Even if the distinct date sets happen to match, two OHLCV observations
    # for the same session do not form one valid daily bar.
    if len(observed) != len(seen_days):
        duplicate_days = sorted(day for day, count in Counter(seen_days).items() if count > 1)
        unexpected = (*unexpected, *duplicate_days)
    status: CalendarStatus = (
        "MISMATCH_PINNED_NYSE_PUBLIC_SCHEDULE" if missing or unexpected
        else "MATCHED_PINNED_NYSE_PUBLIC_SCHEDULE"
    )
    return _result(
        status, begin, end, len(expected), len(seen_days), missing, unexpected
    )
