"""Market-data lineage is required for auditable point-in-time claims."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataContractError, MarketDataSet, MarketSourceProvenance
from core.data.parquet import ParquetDataProvider
from core.data.quality import market_data_quality


def dataset(provenance: MarketSourceProvenance | None = None) -> MarketDataSet:
    bars = (
        Bar(datetime(2024, 1, 2, tzinfo=timezone.utc), "AAA", 100, 102, 99, 101, 10),
        Bar(datetime(2024, 1, 3, tzinfo=timezone.utc), "AAA", 101, 103, 100, 102, 10),
    )
    return MarketDataSet("sample-v1", "development", bars, provenance=provenance)


def provenance(**kwargs: object) -> MarketSourceProvenance:
    defaults: dict[str, object] = dict(
        source_id="independent-vendor",
        retrieved_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        revision_policy="as_of",
        universe_policy="point_in_time",
        corporate_action_policy="split_adjusted",
        corporate_action_reference="actions-asof-v4",
        includes_delisted=True,
    )
    defaults.update(kwargs)
    return MarketSourceProvenance(**defaults)  # type: ignore[arg-type]


def test_absent_provenance_is_unverified_not_implicitly_pit() -> None:
    report = market_data_quality(dataset())
    assert report.status == "UNVERIFIED"
    assert "provenance_missing" in report.issues
    assert report.point_in_time_verified is False


def test_pit_declaration_requires_revision_universe_actions_and_delisted() -> None:
    safe = provenance()
    report = market_data_quality(dataset(safe))
    assert report.status == "DECLARED_POINT_IN_TIME"
    assert report.point_in_time_verified is False  # Declaration is not independent audit.
    issues = market_data_quality(
        dataset(
            provenance(
                revision_policy="latest",
                universe_policy="current_constituents",
                corporate_action_policy="raw",
                corporate_action_reference=None,
                includes_delisted=False,
            )
        )
    ).issues
    assert set(issues) >= {
        "revisions_not_as_of",
        "survivorship_risk",
        "delisted_assets_missing",
        "corporate_action_adjustment_unverified",
    }


def test_provenance_is_part_of_hash_and_parquet_roundtrip(tmp_path: Path) -> None:
    original = dataset(provenance())
    old = dataset()
    assert original.dataset_hash != old.dataset_hash
    assert original.dataset_hash != dataset(provenance(source_id="other-vendor")).dataset_hash
    target = tmp_path / "data.parquet"
    ParquetDataProvider.write(target, original)
    restored = ParquetDataProvider.read(target)
    assert restored.provenance == original.provenance
    assert restored.dataset_hash == original.dataset_hash
    assert market_data_quality(restored).status == "DECLARED_POINT_IN_TIME"


def test_provenance_rejects_invalid_dates_enums_and_impossible_snapshot_time() -> None:
    with pytest.raises(DataContractError, match="timezone"):
        provenance(retrieved_at=datetime(2024, 2, 1))
    with pytest.raises(DataContractError, match="revision"):
        provenance(revision_policy="magic")
    with pytest.raises(DataContractError, match="snapshot"):
        dataset(provenance(retrieved_at=datetime(2023, 12, 1, tzinfo=timezone.utc)))


def test_legacy_market_dataset_hash_is_unchanged() -> None:
    from core.integrity.hashes import content_hash

    old = dataset()
    assert old.dataset_hash == content_hash(
        {
            "version": old.version,
            "zone": "development",
            "bars": [bar.record() for bar in old.bars],
        }
    )


def test_invalid_provenance_metadata_fails_closed_before_using_vendor_claim() -> None:
    valid = provenance().record()
    with pytest.raises(DataContractError, match="metadata"):
        MarketSourceProvenance.from_record({**valid, "revision_policy": ["as_of"]})
    with pytest.raises(DataContractError, match="metadata"):
        MarketSourceProvenance.from_record({**valid, "source_id": 42})


def test_missing_continuous_daily_session_is_reported_not_silently_filled() -> None:
    bars = (
        Bar(datetime(2024, 1, 2, tzinfo=timezone.utc), "BTC", 100, 101, 99, 100, 10),
        Bar(datetime(2024, 1, 4, tzinfo=timezone.utc), "BTC", 100, 101, 99, 100, 10),
    )
    result = market_data_quality(
        MarketDataSet(
            "crypto-v1",
            "development",
            bars,
            timeframe="1d",
            calendar="continuous",
            provenance=provenance(universe_policy="single_symbol"),
        )
    )
    assert "missing_continuous_bars" in result.issues
    assert result.status == "UNVERIFIED"


def test_us_exchange_weekend_is_not_mistaken_for_missing_24h_bars() -> None:
    bars = (
        Bar(datetime(2024, 1, 5, tzinfo=timezone.utc), "AAA", 100, 101, 99, 100, 10),
        Bar(datetime(2024, 1, 8, tzinfo=timezone.utc), "AAA", 100, 101, 99, 100, 10),
    )
    result = market_data_quality(
        MarketDataSet(
            "us-v1",
            "development",
            bars,
            provenance=provenance(universe_policy="single_symbol"),
        )
    )
    assert "missing_continuous_bars" not in result.issues


def test_missing_continuous_intraday_bar_is_reported_per_symbol() -> None:
    bars = (
        Bar(datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc), "BTC", 100, 101, 99, 100, 10),
        Bar(datetime(2024, 1, 2, 0, 30, tzinfo=timezone.utc), "BTC", 100, 101, 99, 100, 10),
    )
    result = market_data_quality(
        MarketDataSet(
            "crypto-15m",
            "development",
            bars,
            timeframe="15m",
            calendar="continuous",
            provenance=provenance(universe_policy="single_symbol"),
        )
    )
    assert "missing_continuous_bars" in result.issues


def test_us_equities_long_gap_is_reported_as_warning_without_fake_sessions() -> None:
    """Long gaps are suspicious, but the quality checker does not invent exchange days."""
    bars = (
        Bar(datetime(2024, 1, 2, tzinfo=timezone.utc), "AAA", 100, 101, 99, 100, 10),
        Bar(datetime(2024, 1, 15, tzinfo=timezone.utc), "AAA", 100, 101, 99, 100, 10),
    )
    report = market_data_quality(
        MarketDataSet(
            "sparse-equities", "development", bars,
            provenance=provenance(universe_policy="single_symbol"),
        )
    )
    assert report.status == "UNVERIFIED"
    assert "unusually_long_exchange_gap" in report.issues
    assert report.point_in_time_verified is False
