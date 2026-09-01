from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.data.access import DataAccessDenied, DataZone, InMemoryDataProvider
from core.data.contracts import Bar, DataContractError, MarketDataSet


def bars() -> tuple[Bar, ...]:
    return (
        Bar(datetime(2024, 1, 1, tzinfo=timezone.utc), "TEST", 100, 101, 99, 100.5, 1000),
        Bar(datetime(2024, 1, 2, tzinfo=timezone.utc), "TEST", 100.5, 102, 100, 101, 1100),
    )


def test_market_data_contract_is_versioned_and_sorted() -> None:
    dataset = MarketDataSet("data-v1", "development", bars())

    assert dataset.dataset_hash
    assert dataset.zone is DataZone.DEVELOPMENT
    assert dataset.bars[0].timestamp < dataset.bars[1].timestamp


def test_market_data_rejects_naive_or_duplicate_bars() -> None:
    with pytest.raises(DataContractError, match="timezone"):
        Bar(datetime(2024, 1, 1), "TEST", 1, 1, 1, 1, 1)
    duplicate = bars() + (bars()[1],)
    with pytest.raises(DataContractError, match="duplicate"):
        MarketDataSet("data-v1", "development", duplicate)


def test_research_cannot_read_sealed_oos() -> None:
    provider = InMemoryDataProvider(
        development=MarketDataSet("dev", "development", bars()),
        validation=MarketDataSet("val", "validation", bars()),
        sealed_oos=MarketDataSet("oos", "sealed_oos", bars()),
    )

    assert provider.read(DataZone.DEVELOPMENT, role="research").version == "dev"
    with pytest.raises(DataAccessDenied, match="sealed"):
        provider.read(DataZone.SEALED_OOS, role="research")
    assert provider.read(DataZone.SEALED_OOS, role="promotion_gate").version == "oos"
