"""Secondary split catalogs and cash-adjustment residuals cannot certify PIT."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine import qqq_split_residual_audit as split_audit


def _pair(dates: list[str], dividends: list[float], extra_factor: dict[str, float] | None = None):
    extra_factor = extra_factor or {}
    source = MarketSourceProvenance(
        source_id="tiingo", retrieved_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        revision_policy="latest", universe_policy="single_symbol",
        corporate_action_policy="raw", corporate_action_reference=None,
        includes_delisted=False,
    )
    raw = []
    adjusted = []
    factor = .91
    for date, cash in zip(dates, dividends, strict=True):
        factor *= (1 + cash/100) * extra_factor.get(date, 1.0)
        stamp = datetime.fromisoformat(date + "T00:00:00+00:00")
        raw.append(Bar(stamp, "QQQ", 100, 101, 99, 100, 1000))
        adjusted.append(Bar(stamp, "QQQ", 100*factor, 101*factor, 99*factor, 100*factor, 1000))
    return (
        MarketDataSet("sample", DataZone.DEVELOPMENT, tuple(raw), provenance=source),
        MarketDataSet(
            "sample", DataZone.DEVELOPMENT, tuple(adjusted),
            provenance=replace(source, corporate_action_policy="total_return_adjusted"),
        ),
    )


def test_secondary_split_catalog_only_2000_event_outside_requested_period():
    catalog = split_audit.load_qqq_split_history_secondary_v1()
    assert catalog["split_events"] == [{"date": "2000-03-20", "numerator": 2, "denominator": 1}]
    assert len(catalog["sources"]) >= 2
    assert catalog["evidence_class"] == "SECONDARY_AGGREGATOR_ONLY"


def test_cash_accounted_for_and_split_absence_is_not_certified():
    raw, adjusted = _pair(
        ["2025-03-21", "2025-03-24", "2025-03-25"],
        [0, .71571, 0],
    )
    report = split_audit.audit_qqq_split_residuals(raw, adjusted)
    assert report.status == "NO_UNEXPLAINED_FACTOR_EVENTS"
    assert report.cash_events_matched == 1
    assert report.potential_split_or_revision_events == 0
    assert report.known_split_events_in_window == 0
    assert report.secondary_split_catalog_sources == 2
    assert report.full_reference_window_covered is False
    assert report.primary_split_history_verified is False
    assert report.point_in_time_price_verified is False
    assert report.broker_executable is False
    assert report.record()["potential_split_or_revision_events"] == 0


def test_split_like_jump_never_hidden_as_cash_dividend():
    raw, adjusted = _pair(
        ["2025-03-21", "2025-03-24", "2025-03-25"],
        [0, .71571, 0], {"2025-03-25": 2},
    )
    report = split_audit.audit_qqq_split_residuals(raw, adjusted)
    assert report.status == "UNEXPLAINED_FACTOR_EVENTS"
    assert report.potential_split_or_revision_events == 1
    assert report.potential_event_dates == ("2025-03-25",)
    assert report.maximum_cash_equivalent_residual_usd > 10
    assert report.primary_split_history_verified is False


def test_missing_issuer_cash_event_and_cross_vendor_fail_closed():
    raw, adj = _pair(["2025-03-21", "2025-03-25"], [0, 0])
    result = split_audit.audit_qqq_split_residuals(raw, adj)
    assert result.status == "INCOMPLETE_ISSUER_CASH_OBSERVATIONS"
    assert result.missing_cash_event_dates == ("2025-03-24",)
    assert split_audit.audit_qqq_split_residuals(
        raw, replace(adj, provenance=replace(adj.provenance, source_id="other"))
    ).status == "NOT_COMPARABLE"
    assert split_audit.audit_qqq_split_residuals(raw, raw).status == "NOT_COMPARABLE"


def test_reference_tampering_fails_closed(tmp_path: Path, monkeypatch):
    raw, adjusted = _pair(["2025-03-21", "2025-03-24"], [0, .71571])
    bogus = tmp_path / "split.json"
    bogus.write_text("{}")
    monkeypatch.setattr(split_audit, "_REFERENCE", bogus)
    with pytest.raises(ValueError, match="integrity"):
        split_audit.audit_qqq_split_residuals(raw, adjusted)
