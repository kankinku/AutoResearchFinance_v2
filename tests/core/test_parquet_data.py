from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.data.contracts import Bar, MarketDataSet
from core.data.parquet import ParquetDataProvider


def test_parquet_round_trip_preserves_contract_and_hash(tmp_path: Path) -> None:
    dataset = MarketDataSet(
        "data-v2",
        "validation",
        (
            Bar(datetime(2024, 1, 1, tzinfo=timezone.utc), "TEST", 10, 11, 9, 10.5, 100),
            Bar(datetime(2024, 1, 2, tzinfo=timezone.utc), "TEST", 10.5, 12, 10, 11.5, 120),
        ),
    )
    path = tmp_path / "bars.parquet"

    ParquetDataProvider.write(path, dataset)
    loaded = ParquetDataProvider.read(path)

    assert loaded.version == dataset.version
    assert loaded.zone == dataset.zone
    assert loaded.dataset_hash == dataset.dataset_hash
