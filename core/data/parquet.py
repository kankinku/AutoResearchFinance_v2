from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.data.contracts import Bar, DataZone, MarketDataSet, SeriesDataSet, SeriesObservation


class ParquetDataProvider:
    """Versioned local Parquet storage for immutable research datasets."""

    @staticmethod
    def write(path: Path, dataset: MarketDataSet) -> None:
        import pandas as pd  # type: ignore[import-untyped]
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as parquet  # type: ignore[import-untyped]

        path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame([bar.record() for bar in dataset.bars])
        table = pa.Table.from_pandas(frame, preserve_index=False)
        metadata = dict(table.schema.metadata or {})
        metadata.update(
            {
                b"dataset_version": dataset.version.encode(),
                b"data_zone": DataZone(dataset.zone).value.encode(),
            }
        )
        parquet.write_table(table.replace_schema_metadata(metadata), path)

    @staticmethod
    def read(path: Path) -> MarketDataSet:
        import pandas as pd

        if not path.is_file():
            raise FileNotFoundError(path)
        frame = pd.read_parquet(path, engine="pyarrow")
        metadata = _metadata(path)
        required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
        if not required.issubset(frame.columns):
            raise ValueError("Parquet file does not satisfy the bar schema")
        bars = tuple(
            Bar(
                datetime.fromisoformat(str(row.timestamp)),
                str(row.symbol),
                float(row.open),
                float(row.high),
                float(row.low),
                float(row.close),
                float(row.volume),
            )
            for row in frame.itertuples(index=False)
        )
        return MarketDataSet(metadata["dataset_version"], metadata["data_zone"], bars)

    @staticmethod
    def write_series(path: Path, dataset: SeriesDataSet) -> None:
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as parquet

        path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame([observation.record() for observation in dataset.observations])
        table = pa.Table.from_pandas(frame, preserve_index=False)
        metadata = dict(table.schema.metadata or {})
        metadata.update(
            {
                b"dataset_version": dataset.version.encode(),
                b"data_zone": DataZone(dataset.zone).value.encode(),
                b"dataset_kind": b"series",
            }
        )
        parquet.write_table(table.replace_schema_metadata(metadata), path)

    @staticmethod
    def read_series(path: Path) -> SeriesDataSet:
        import pandas as pd

        if not path.is_file():
            raise FileNotFoundError(path)
        frame = pd.read_parquet(path, engine="pyarrow")
        metadata = _metadata(path)
        required = {"timestamp", "series_id", "value", "available_at"}
        if not required.issubset(frame.columns):
            raise ValueError("Parquet file does not satisfy the series schema")
        observations = tuple(
            SeriesObservation(
                str(row.series_id),
                datetime.fromisoformat(str(row.timestamp)),
                float(row.value),
                datetime.fromisoformat(str(row.available_at)) if row.available_at else None,
            )
            for row in frame.itertuples(index=False)
        )
        return SeriesDataSet(metadata["dataset_version"], metadata["data_zone"], observations)


def _metadata(path: Path) -> dict[str, str]:
    import pyarrow.parquet as parquet

    raw = parquet.read_metadata(path).metadata or {}
    decoded = {key.decode(): value.decode() for key, value in raw.items()}
    try:
        return {
            "dataset_version": decoded["dataset_version"],
            "data_zone": decoded["data_zone"],
        }
    except KeyError as exc:
        raise ValueError("Parquet metadata must include dataset_version and data_zone") from exc
