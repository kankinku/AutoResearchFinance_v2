"""External price-reference reconciliation must remain diagnostic, never PIT approval."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine.benchmark_reconciliation import (
    reconcile_development_benchmark,
)
from research.indicator_engine.catalog import ResearchCatalogError


def _market(
    provider: str = "first_vendor",
    *,
    zone: DataZone = DataZone.DEVELOPMENT,
    revision: str = "latest",
    adjustment: str = "raw",
    symbol: str = "QQQ",
    offset_minutes: int = 0,
    skip_day: int | None = None,
    gain: float = 0.0,
    duplicate_session: bool = False,
) -> MarketDataSet:
    start = datetime(2023, 1, 2, 20, tzinfo=timezone.utc)
    bars = [
        Bar(start + timedelta(days=i, minutes=offset_minutes), symbol,
            100 + i + gain, 101 + i + gain, 99 + i + gain,
            100 + i + gain, 1000)
        for i in range(25) if i != skip_day
    ]
    if duplicate_session:
        bars.append(Bar(start + timedelta(minutes=10), symbol, 100, 101, 99, 100, 1000))
        bars.sort(key=lambda b: b.timestamp)
    prov = MarketSourceProvenance(
        provider, datetime(2026, 10, 14, tzinfo=timezone.utc),
        revision, "single_symbol", adjustment,
        "corporate-action-ledger" if adjustment != "raw" else None, False,
    )
    return MarketDataSet("fixture", zone, tuple(bars), provenance=prov)


def test_two_vendor_aligned_prices_are_only_cross_source_diagnostic():
    primary = _market()
    second = _market("other_vendor", offset_minutes=20, gain=0.4)
    report = reconcile_development_benchmark(primary, second)
    assert report.overlap_sessions == 25
    assert report.primary_sessions == report.reference_sessions == 25
    assert report.primary_only_sessions == report.reference_only_sessions == 0
    assert report.status == "CROSS_SOURCE_DEVELOPMENT_ONLY"
    assert "latest_revision_not_as_of" in report.blockers
    assert "vendor_authenticity_not_verified" in report.blockers
    assert "corporate_action_adjustment_unverified" in report.blockers
    assert not report.independent_benchmark_verified
    assert not report.point_in_time_verified
    assert not report.candidate_promotable
    assert report.reference_first_open == pytest.approx(100.4)
    assert report.primary_price_only_final_equity is not None
    assert report.reference_price_only_final_equity is not None
    assert report.reference_hash != primary.dataset_hash
    assert report.reconciliation_hash == (
        reconcile_development_benchmark(primary, second).reconciliation_hash
    )
    assert report.max_absolute_close_difference == pytest.approx(0.4)
    assert report.max_relative_close_difference is not None
    assert dict(report.field_mismatch_counts)["close"] == 25
    assert dict(report.field_mismatch_counts)["volume"] == 0


def test_same_vendor_is_not_independent_even_with_different_price_bytes():
    primary = _market()
    second = _market(gain=5)
    report = reconcile_development_benchmark(primary, second)
    assert report.status == "RECONCILIATION_BLOCKED"
    assert "same_vendor_identity" in report.blockers
    assert report.primary_price_only_final_equity is None
    assert report.reference_price_only_final_equity is None


def test_session_gaps_are_reported_without_padded_or_silent_interpolation():
    report = reconcile_development_benchmark(_market(), _market("other", skip_day=6))
    assert report.status == "RECONCILIATION_BLOCKED"
    assert "incomplete_session_alignment" in report.blockers
    assert report.primary_only_sessions == 1
    assert report.reference_only_sessions == 0
    assert report.overlap_sessions == 24
    assert report.primary_price_only_final_equity is None


def test_adjustment_mismatch_blocks_comparison_even_when_prices_seem_aligned():
    report = reconcile_development_benchmark(
        _market(), _market("other", adjustment="split_adjusted")
    )
    assert report.status == "RECONCILIATION_BLOCKED"
    assert "incompatible_corporate_action_conventions" in report.blockers


def test_verified_metadata_never_converts_an_audit_into_pit_certificate():
    report = reconcile_development_benchmark(
        _market(revision="as_of", adjustment="total_return_adjusted"),
        _market("other", revision="as_of", adjustment="total_return_adjusted", gain=0.01),
    )
    assert report.status == "CROSS_SOURCE_DEVELOPMENT_ONLY"
    assert "latest_revision_not_as_of" not in report.blockers
    assert not report.point_in_time_verified
    assert not report.independent_benchmark_verified
    assert "bar_level_availability_unverified" in report.blockers


def test_mutation_changes_identity_and_same_bytes_cannot_pretend_independence():
    primary = _market()
    reference = _market("other", gain=0.2)
    normal = reconcile_development_benchmark(primary, reference)
    bars = list(reference.bars)
    bars[-1] = replace(bars[-1], close=bars[-1].close + 0.1,
                       high=bars[-1].high + 0.1)
    altered = MarketDataSet(reference.version, reference.zone, tuple(bars),
                            provenance=reference.provenance)
    assert normal.reconciliation_hash != reconcile_development_benchmark(
        primary, altered
    ).reconciliation_hash
    same_bars = MarketDataSet(primary.version, primary.zone, primary.bars,
                              provenance=_market("other").provenance)
    report = reconcile_development_benchmark(primary, same_bars)
    assert "identical_ohlcv_payload" in report.blockers
    assert report.status == "RECONCILIATION_BLOCKED"


def test_rejects_wrong_scope_missing_provenance_and_bad_cash():
    primary = _market()
    reference = _market("other")
    with pytest.raises(ResearchCatalogError, match="development"):
        reconcile_development_benchmark(primary, _market("other", zone=DataZone.SEALED_OOS))
    with pytest.raises(ResearchCatalogError, match="symbol"):
        reconcile_development_benchmark(primary, _market("other", symbol="SPY"))
    with pytest.raises(ResearchCatalogError, match="cash"):
        reconcile_development_benchmark(primary, reference, initial_cash=float("inf"))
    with pytest.raises(ResearchCatalogError, match="provenance"):
        reconcile_development_benchmark(
            MarketDataSet(primary.version, primary.zone, primary.bars), reference
        )
    with pytest.raises(ResearchCatalogError, match="duplicate"):
        reconcile_development_benchmark(primary, _market("other", duplicate_session=True))


def test_manual_parquet_cli_never_creates_research_database(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from core.data.parquet import ParquetDataProvider
    from research.indicator_engine.cli import main

    first = tmp_path / "primary.parquet"
    second = tmp_path / "secondary.parquet"
    ParquetDataProvider.write(first, _market())
    ParquetDataProvider.write(second, _market("second_vendor", gain=0.4))
    monkeypatch.setattr(sys, "argv", [
        "research-cli", "audit-benchmark", str(first), str(second),
    ])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "CROSS_SOURCE_DEVELOPMENT_ONLY"
    assert report["candidate_promotable"] is False
    assert report["independent_benchmark_verified"] is False
    assert not (tmp_path / "research.sqlite").exists()

    ParquetDataProvider.write(second, _market())
    assert main() == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["status"] == "RECONCILIATION_BLOCKED"


def test_catalog_cli_still_requires_database(tmp_path, monkeypatch):
    import sys

    from research.indicator_engine.cli import main

    monkeypatch.setattr(sys, "argv", ["research-cli", "status"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_provider_session_date_label_and_exchange_close_align_without_one_day_shift():
    """Legacy Tiingo timestamps encode YYYY-MM-DD midnight UTC as date labels."""
    from datetime import time
    from zoneinfo import ZoneInfo

    ny = ZoneInfo("America/New_York")
    a = _market("first_vendor")
    close_bars = tuple(
        replace(bar, timestamp=datetime.combine(bar.timestamp.date(), time(16), tzinfo=ny))
        for bar in _market("second_vendor", gain=0.2).bars
    )
    b = MarketDataSet("fixture", DataZone.DEVELOPMENT, close_bars,
                      provenance=_market("second_vendor").provenance)
    result = reconcile_development_benchmark(a, b)
    assert result.overlap_sessions == 25
    assert result.primary_only_sessions == result.reference_only_sessions == 0
    assert result.status == "CROSS_SOURCE_DEVELOPMENT_ONLY"


def test_midnight_utc_daily_date_labels_align_with_ny_close_timestamps():
    from zoneinfo import ZoneInfo

    source = _market()
    midnight_bars = tuple(replace(bar, timestamp=datetime(
        bar.timestamp.year, bar.timestamp.month, bar.timestamp.day,
        tzinfo=timezone.utc
    )) for bar in source.bars)
    primary = MarketDataSet(source.version, source.zone, midnight_bars,
                            provenance=source.provenance)
    other = _market("another-provider", gain=0.2)
    bars = tuple(replace(bar, timestamp=datetime(
        bar.timestamp.year, bar.timestamp.month, bar.timestamp.day, 16,
        tzinfo=ZoneInfo("America/New_York")
    )) for bar in other.bars)
    exchange_closes = MarketDataSet(other.version, other.zone, bars,
                                    provenance=other.provenance)
    result = reconcile_development_benchmark(primary, exchange_closes)
    assert result.primary_only_sessions == 0
    assert result.reference_only_sessions == 0
    assert result.overlap_sessions == len(primary.bars)
