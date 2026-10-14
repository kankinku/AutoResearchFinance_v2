"""Research data quality must not be promoted by an in-sample reference."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.market_audit import inspect_development_market_reference


def _prices(*, zone: DataZone = DataZone.DEVELOPMENT, as_of: bool = False):
    t0 = datetime(2020, 1, 1, 21, tzinfo=timezone.utc)
    bars = tuple(Bar(t0+timedelta(days=i), "QQQ", 100.0+i, 101.0+i,
                     99.0+i, 100.0+i, 1000) for i in range(20))
    provenance = MarketSourceProvenance(
        "tiingo", datetime(2026, 10, 10, tzinfo=timezone.utc),
        "as_of" if as_of else "latest", "single_symbol", "raw", None, False,
    )
    return MarketDataSet("demo", zone, bars, provenance=provenance)


def test_latest_raw_development_reference_is_math_only_with_fail_closed_pit():
    data = _prices()
    diagnostic = inspect_development_market_reference(data)
    assert diagnostic.dataset_hash == data.dataset_hash
    assert diagnostic.status == "DEVELOPMENT_REFERENCE_ONLY"
    assert not diagnostic.point_in_time_verified
    assert not diagnostic.independent_benchmark_verified
    assert not diagnostic.candidate_promotable
    assert "latest_revision_not_as_of" in diagnostic.blockers
    assert "corporate_action_adjustment_unverified" in diagnostic.blockers
    assert "independent_vendor_not_authenticated" in diagnostic.blockers
    assert "publication_availability_times_unverified" in diagnostic.blockers
    # Buy first open, pay one set of costs, mark last close. No fictitious
    # final liquidation or cash distributions, same convention as strategy.
    expected = 10_000 / (1 + 0.0008) / 100.0 * 119.0
    assert diagnostic.price_only_marked_equity == pytest.approx(expected)
    assert diagnostic.purchase_cost == pytest.approx(10_000-10_000/(1 + 0.0008))


def test_even_vendor_as_of_metadata_does_not_prove_pit_or_independence():
    data = _prices(as_of=True)
    diagnostic = inspect_development_market_reference(data)
    assert "latest_revision_not_as_of" not in diagnostic.blockers
    assert "independent_vendor_not_authenticated" in diagnostic.blockers
    assert not diagnostic.point_in_time_verified
    assert not diagnostic.independent_benchmark_verified


def test_rejects_sealed_or_cross_asset_input():
    with pytest.raises(ResearchCatalogError, match="development"):
        inspect_development_market_reference(_prices(zone=DataZone.SEALED_OOS))
    data = _prices()
    bars = list(data.bars)
    bars = [replace(bars[4], symbol="AAA"), *bars]
    with pytest.raises(ResearchCatalogError, match="single-symbol"):
        inspect_development_market_reference(
            MarketDataSet(data.version, data.zone, tuple(bars), provenance=data.provenance)
        )
