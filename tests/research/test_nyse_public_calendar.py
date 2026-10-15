"""Pinned official NYSE public holidays: strict dates, provenance and no PIT promotion."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine import nyse_public_calendar as official
from research.indicator_engine.nyse_public_calendar import verify_published_nyse_regular_sessions


def _days(*days: str, symbol: str = "QQQ") -> MarketDataSet:
    return MarketDataSet("calendar-synthetic", DataZone.DEVELOPMENT, tuple(
        Bar(datetime.combine(date.fromisoformat(value), datetime.min.time(), timezone.utc),
            symbol, 100., 101., 99., 100., 10_000.)
        for value in days
    ))


@pytest.mark.parametrize(("days", "start", "end", "expected"), [
    (("2025-01-08", "2025-01-10"), "2025-01-08", "2025-01-10", 2),
    (("2021-06-18", "2021-06-21"), "2021-06-18", "2021-06-21", 2),
    (("2022-01-03", "2022-01-04"), "2022-01-03", "2022-01-04", 2),
    (("2022-06-17", "2022-06-21"), "2022-06-17", "2022-06-21", 2),
    (("2026-07-02", "2026-07-06"), "2026-07-02", "2026-07-06", 2),
])
def test_official_holidays_observed_and_special_closures(days, start, end, expected):
    report = verify_published_nyse_regular_sessions(
        _days(*days), requested_start=date.fromisoformat(start),
        requested_end=date.fromisoformat(end),
    )
    assert report.status == "MATCHED_PINNED_NYSE_PUBLIC_SCHEDULE"
    assert report.expected_sessions == expected
    assert report.observed_sessions == expected
    assert report.missing_count == 0
    assert report.unexpected_count == 0
    assert report.regular_session_schedule_matched is True
    assert report.point_in_time_price_verified is False
    assert report.corporate_actions_verified is False
    assert report.broker_executable is False


def test_missing_observed_trading_day_and_forbidden_holiday_bar_fail():
    partial = verify_published_nyse_regular_sessions(
        _days("2025-01-08"),
        requested_start=date(2025, 1, 8), requested_end=date(2025, 1, 10),
    )
    assert partial.status == "MISMATCH_PINNED_NYSE_PUBLIC_SCHEDULE"
    assert partial.missing_sessions == ("2025-01-10",)
    extra = verify_published_nyse_regular_sessions(
        _days("2025-01-08", "2025-01-09", "2025-01-10"),
    )
    assert extra.unexpected_sessions == ("2025-01-09",)
    assert not extra.regular_session_schedule_matched


def test_comparison_is_limited_to_requested_boundaries_and_covered_years():
    # Observed edges could be incomplete. The filename's requested dates
    # are necessary to catch missing first/last regular sessions.
    observed = verify_published_nyse_regular_sessions(
        _days("2025-01-08"), requested_start=date(2025, 1, 7),
        requested_end=date(2025, 1, 8),
    )
    assert observed.missing_sessions == ("2025-01-07",)
    out = verify_published_nyse_regular_sessions(
        _days("2027-01-04"),
    )
    assert out.status == "OUTSIDE_PINNED_YEARS"
    assert not out.regular_session_schedule_matched
    assert out.comparison_scope == "observed_first_to_last_only"


def test_one_symbol_session_mismatch_and_ambiguous_utc_midnight_are_rejected():
    valid = _days("2024-01-02", "2024-01-03")
    altered = list(valid.bars)
    altered[0] = replace(altered[0], timestamp=altered[0].timestamp + timedelta(hours=6))
    raw = MarketDataSet(valid.version, valid.zone, tuple(altered))
    unsupported = verify_published_nyse_regular_sessions(raw)
    assert unsupported.status == "UNSUPPORTED_SESSION_LABELS"
    assert not unsupported.regular_session_schedule_matched
    mult = MarketDataSet(valid.version, valid.zone,
        tuple(sorted((*valid.bars, *(_days("2024-01-02", symbol="SPY").bars)),
                     key=lambda b: (b.symbol,b.timestamp))))
    assert verify_published_nyse_regular_sessions(mult).status == "UNSUPPORTED_MARKET_DATA"


def test_hash_pin_tampering_fails_closed(tmp_path: Path, monkeypatch):
    p = tmp_path / "nyse-bogus.json"
    p.write_text('{"schema":"curated_nyse_public_closures_v1"}')
    monkeypatch.setattr(official, "_FILENAME", p)
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify_published_nyse_regular_sessions(_days("2025-01-08", "2025-01-10"))


def test_pinned_public_schedule_never_claims_price_pit_or_broker():
    r = verify_published_nyse_regular_sessions(_days("2025-01-08", "2025-01-10"))
    rec = r.record()
    assert rec["calendar_reference_is_exchange_public_notice"] is True
    assert rec["regular_session_schedule_matched"] is True
    assert rec["independent_historical_price_pit_verified"] is False
    assert rec["corporate_actions_verified"] is False
    assert rec["broker_executable"] is False
