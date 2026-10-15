"""Observational revision detection never certifies historical point-in-time prices."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine.snapshot_revisions import compare_collected_market_snapshots


def _pair():
    base = datetime(2024, 1, 2, tzinfo=timezone.utc)
    bars = tuple(
        Bar(base + timedelta(days=i), "QQQ", 100+i, 102+i, 99+i, 101+i, 2000)
        for i in range(3)
    )
    early = MarketSourceProvenance(
        source_id="tiingo", retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        revision_policy="latest", universe_policy="single_symbol",
        corporate_action_policy="raw", corporate_action_reference=None,
        includes_delisted=False,
    )
    a = MarketDataSet("rev", DataZone.DEVELOPMENT, bars, provenance=early)
    b = replace(a, provenance=replace(early, retrieved_at=early.retrieved_at +
                                      timedelta(days=45)))
    return a, b


def test_same_vendor_future_collection_can_detect_price_revisions():
    before, after = _pair()
    changed = list(after.bars)
    change = changed[1]
    changed[1] = replace(change, close=change.close+0.25)
    later = replace(after, bars=tuple(changed))
    got = compare_collected_market_snapshots(before, later)
    assert got.status == "HISTORICAL_ROWS_REVISED"
    assert got.comparable_bars == 3
    assert got.changed_bars == 1
    assert got.changed_date_examples == ("2024-01-03",)
    assert got.maximum_relative_difference > 0
    assert got.historical_point_in_time_price_verified is False
    assert got.broker_executable is False
    assert got == compare_collected_market_snapshots(before, later)


def test_equal_rows_are_only_vendor_observations_not_pit():
    before, after = _pair()
    report = compare_collected_market_snapshots(before, after)
    assert report.status == "OVERLAPPING_ROWS_UNCHANGED"
    assert report.changed_bars == 0
    assert report.historical_point_in_time_price_verified is False
    assert report.independence == "SAME_VENDOR_DECLARED_SNAPSHOT_TIMES"


def test_requires_ordered_vendor_policy_and_overlapping_sessions():
    before, later = _pair()
    reversed_time = compare_collected_market_snapshots(later, before)
    assert reversed_time.status == "UNORDERED_SNAPSHOT_TIMES"
    assert reversed_time.comparable_bars == 0
    same_time = compare_collected_market_snapshots(before, before)
    assert same_time.status == "UNORDERED_SNAPSHOT_TIMES"
    different_policy = replace(later, provenance=replace(
        later.provenance, corporate_action_policy="total_return_adjusted",
        corporate_action_reference="https://www.tiingo.com/documentation/end-of-day",
    ))
    assert compare_collected_market_snapshots(
        before, different_policy
    ).status == "INCOMPARABLE_SNAPSHOTS"
    late_days = tuple(replace(x, timestamp=x.timestamp+timedelta(days=11))
                      for x in later.bars)
    other_period = replace(later, bars=late_days)
    assert compare_collected_market_snapshots(
        before, other_period
    ).status == "NO_OVERLAPPING_SESSIONS"
