from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash


@dataclass(frozen=True)
class GenerationResults:
    generation: int
    records: tuple[dict[str, Any], ...]
    checksum: str


class ExperimentResultStore:
    @staticmethod
    def write_generation(
        path: Path, generation: int, records: tuple[dict[str, Any], ...]
    ) -> str:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as parquet  # type: ignore[import-untyped]

        if generation < 0 or not records:
            raise ValueError("generation must be non-negative and records cannot be empty")
        normalized = tuple(dict(sorted(record.items())) for record in records)
        scalar_values = (
            value for record in normalized for value in record.values()
        )
        if any(
            not isinstance(value, (str, int, float, bool, type(None)))
            for value in scalar_values
        ):
            raise ValueError("result records must contain scalar values")
        checksum = content_hash(normalized)
        columns = sorted({key for record in normalized for key in record})
        rows = [{key: record.get(key) for key in columns} for record in normalized]
        table = pa.Table.from_pylist(rows)
        metadata = dict(table.schema.metadata or {})
        metadata.update(
            {
                b"generation": str(generation).encode(),
                b"records_hash": checksum.encode(),
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        parquet.write_table(table.replace_schema_metadata(metadata), temporary)
        temporary.replace(path)
        return checksum

    @staticmethod
    def read_generation(path: Path) -> GenerationResults:
        import pyarrow.parquet as parquet

        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            metadata = parquet.read_metadata(path).metadata or {}
            decoded = {key.decode(): value.decode() for key, value in metadata.items()}
            records = tuple(
                dict(sorted(record.items()))
                for record in parquet.read_table(path).to_pylist()
            )
        except Exception as exc:
            raise ValueError("result Parquet checksum verification failed") from exc
        if "generation" not in decoded or "records_hash" not in decoded:
            raise ValueError("result Parquet metadata is incomplete")
        checksum = content_hash(records)
        if checksum != decoded["records_hash"]:
            raise ValueError("result Parquet checksum mismatch")
        return GenerationResults(int(decoded["generation"]), records, checksum)
