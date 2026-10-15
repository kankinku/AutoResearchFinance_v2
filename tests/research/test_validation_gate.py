"""Research validation gate: executable abstention and anomaly evidence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine.forward_window import evaluate_chronological_window
from research.indicator_engine.validation_gate import (
    forward_research_blockers,
    inspect_us_equity_daily_observations,
)
from tests.research.test_academic_algorithm_plan import _catalog, _market, _plan


def _market_source(dataset: MarketDataSet, *, as_of: bool = False):
    source = MarketSourceProvenance(
        source_id="research_mock",
        retrieved_at=datetime(2035, 1, 1, tzinfo=timezone.utc),
        revision_policy="as_of" if as_of else "latest",
        universe_policy="single_symbol",
        corporate_action_policy="total_return_adjusted",
        corporate_action_reference="https://example.org/vendor_adjustments",
        includes_delisted=False,
    )
    return replace(dataset, provenance=source)


def test_weekend_and_duplicate_session_detection_is_not_calendar_certification():
    start = datetime(2026, 1, 2, tzinfo=timezone.utc)  # Friday
    hours = (0, 24, 72, 72 + 6)
    bars = tuple(
        Bar(start + timedelta(hours=h), "QQQ", 100., 101., 99., 100., 1000.)
        for h in hours
    )
    data = MarketDataSet("session", DataZone.DEVELOPMENT, bars)
    scan = inspect_us_equity_daily_observations(data)
    assert scan.weekend_bars == ("QQQ:2026-01-03",)
    assert scan.repeated_session_dates == ("QQQ:2026-01-05",)
    assert scan.max_adjacent_calendar_gap_days == 2
    assert scan.has_obvious_anomaly
    assert scan.record()["calendar_independently_verified"] is False
    assert scan.record()["all_expected_exchange_sessions_verified"] is False


def test_calendar_gaps_do_not_become_invented_missing_sessions():
    start = datetime(2026, 1, 2, tzinfo=timezone.utc)
    days = (0, 3, 14)
    data = MarketDataSet("gaps", DataZone.DEVELOPMENT, tuple(
        Bar(start + timedelta(days=i), "QQQ", 100., 101., 99., 100., 1000.)
        for i in days
    ))
    scan = inspect_us_equity_daily_observations(data)
    assert scan.weekend_bars == ()
    assert scan.repeated_session_dates == ()
    assert scan.max_adjacent_calendar_gap_days == 11
    assert scan.record()["status"] == "SESSION_CALENDAR_NOT_INDEPENDENTLY_VERIFIED"


def test_metrics_above_threshold_never_upgrade_self_declared_as_of_to_pit():
    source = _market()
    hist = _market_source(replace(source, bars=source.bars[:450]), as_of=True)
    forward = _market_source(replace(source, bars=source.bars[450:]), as_of=True)
    reasons = forward_research_blockers(
        hist, forward, cumulative_return=2., sharpe=3., max_drawdown=.01,
        closed_trades=300,
    )
    assert "independent_historical_publication_proof_missing" in reasons
    assert "historical_official_nyse_session_mismatch_or_unavailable" in reasons
    assert "sealed_out_of_sample_approval_missing" in reasons
    assert "insufficient_closed_trades" not in reasons
    assert "forward_revisions_not_as_of" not in reasons
    assert reasons == tuple(sorted(set(reasons)))


def test_unverified_and_unprofitable_forward_independently_surface_reasons(tmp_path: Path):
    catalog = _catalog(tmp_path)
    data = _market()
    hist = replace(data, bars=data.bars[:450])
    forward = replace(data, bars=data.bars[450:])
    result = evaluate_chronological_window(catalog, _plan(), hist, forward)
    reasons = result.validation_blocking_reasons
    assert reasons and reasons == tuple(sorted(set(reasons)))
    assert "historical_market_provenance_missing" in reasons
    assert "forward_market_provenance_missing" in reasons
    assert "short_forward_evaluation_window" in reasons
    assert "independent_historical_publication_proof_missing" in reasons
    assert "historical_official_nyse_session_mismatch_or_unavailable" in reasons
    assert "sealed_out_of_sample_approval_missing" in reasons
    assert result.validation_decision == "NOT_VALIDATED"
    assert result.independent_oos_approved is False
    assert result.candidate_promotable is False
    assert result.broker_executable is False
    assert evaluate_chronological_window(catalog, _plan(), hist, forward) == result
