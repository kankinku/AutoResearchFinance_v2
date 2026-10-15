"""Vendor-declared as-of and raw daily bars never independently prove PIT."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine.historical_vintage_preflight import assess_historical_vintage


def _market(*days: str, policy: str = "latest", provenance: bool = True):
    bars = tuple(
        Bar(datetime.fromisoformat(day + "T00:00:00+00:00"),
            "QQQ", 100, 102, 99, 101, 1000)
        for day in days
    )
    source = MarketSourceProvenance(
        source_id="tiingo",
        retrieved_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        revision_policy=policy, universe_policy="single_symbol",
        corporate_action_policy="raw", corporate_action_reference=None,
        includes_delisted=False,
    )
    return MarketDataSet(
        "unit", DataZone.DEVELOPMENT, bars,
        provenance=source if provenance else None,
    )


def test_unanchored_latest_data_reports_missing_decision_time_and_independent_proof():
    result = assess_historical_vintage(_market("2024-01-02", "2024-01-03"))
    assert result.status == "DECISION_TIME_REQUIRED"
    assert "historical_decision_time_missing" in result.blocking_reasons
    assert "independent_publication_attestation_missing" in result.blocking_reasons
    assert "latest_revision_policy_not_historical_as_of" in result.blocking_reasons
    assert result.sessions_past_assumed_close is None
    assert result.point_in_time_verified is False
    assert result.broker_executable is False


def test_decision_cutoff_detects_retroactive_capture_and_unfinished_daily_bar():
    decision = datetime(2024, 1, 3, 19, tzinfo=timezone.utc)  # 14:00 New York
    result = assess_historical_vintage(
        _market("2024-01-02", "2024-01-03", "2024-01-04"),
        decision_at=decision,
    )
    assert result.status == "CUTOFF_CONFLICT"
    assert result.sessions_past_assumed_close == 1
    assert result.unfinished_or_future_sessions == 2
    assert result.retrieved_after_decision is True
    assert "captured_after_historical_decision" in result.blocking_reasons
    assert "daily_session_not_closed_at_decision" in result.blocking_reasons
    assert result.point_in_time_verified is False


def test_self_declared_as_of_even_after_close_is_not_independent_evidence():
    decision = datetime(2026, 10, 16, tzinfo=timezone.utc)
    result = assess_historical_vintage(
        _market("2024-01-02", "2024-01-03", policy="as_of"),
        decision_at=decision,
    )
    assert result.status == "UNATTESTED_SNAPSHOT"
    assert result.retrieved_after_decision is False
    assert result.sessions_past_assumed_close == 2
    assert result.unfinished_or_future_sessions == 0
    assert "latest_revision_policy_not_historical_as_of" not in result.blocking_reasons
    assert "independent_publication_attestation_missing" in result.blocking_reasons
    assert not result.point_in_time_verified


def test_dst_new_york_close_respects_timestamp_label_not_midnight_utc():
    market = _market("2024-03-08", "2024-03-11")
    # March 11 NYSE regular session closes 20:00 UTC after DST starts.
    exact_close = assess_historical_vintage(
        market, decision_at=datetime(2024, 3, 11, 20, tzinfo=timezone.utc)
    )
    assert exact_close.sessions_past_assumed_close == 1
    assert exact_close.unfinished_or_future_sessions == 1
    after_close = assess_historical_vintage(
        market, decision_at=datetime(2024, 3, 11, 20, 1, tzinfo=timezone.utc)
    )
    assert after_close.sessions_past_assumed_close == 2
    assert after_close.unfinished_or_future_sessions == 0
    assert not after_close.point_in_time_verified


def test_missing_provenance_and_unsupported_daily_timestamp_fail_closed():
    base = _market("2024-01-02", provenance=False)
    missing = assess_historical_vintage(
        base, decision_at=datetime(2024, 2, 1, tzinfo=timezone.utc)
    )
    assert "vendor_provenance_missing" in missing.blocking_reasons
    assert missing.status == "UNATTESTED_SNAPSHOT"

    daily = _market("2024-01-02")
    moved = replace(
        daily.bars[0], timestamp=datetime(2024, 1, 2, 8, tzinfo=timezone.utc)
    )
    changed = assess_historical_vintage(
        replace(daily, bars=(moved,)),
        decision_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
    )
    assert changed.status == "UNSUPPORTED_DAILY_LABEL"
    assert changed.sessions_past_assumed_close is None
    assert "non_midnight_utc_daily_session_label" in changed.blocking_reasons


def test_invalid_timezone_and_sealed_data_refused():
    with pytest.raises(ValueError, match="timezone"):
        assess_historical_vintage(
            _market("2024-01-02"), decision_at=datetime(2024, 2, 1)
        )
    sealed = replace(_market("2024-01-02"), zone=DataZone.SEALED_OOS)
    with pytest.raises(ValueError, match="development"):
        assess_historical_vintage(sealed, decision_at=datetime.now(timezone.utc))
