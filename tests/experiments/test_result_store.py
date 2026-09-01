from __future__ import annotations

from pathlib import Path

import pytest

from experiments.result_store import ExperimentResultStore


def test_generation_result_store_writes_and_verifies_parquet(tmp_path: Path) -> None:
    path = tmp_path / "generation_004.parquet"
    records = ({"candidate_hash": "a", "score": 0.4}, {"candidate_hash": "b", "score": 0.8})

    checksum = ExperimentResultStore.write_generation(path, 4, records)
    loaded = ExperimentResultStore.read_generation(path)

    assert checksum
    assert loaded.generation == 4
    assert loaded.records == records


def test_generation_result_store_rejects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "generation_004.parquet"
    ExperimentResultStore.write_generation(path, 4, ({"candidate_hash": "a", "score": 0.4},))
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        ExperimentResultStore.read_generation(path)
