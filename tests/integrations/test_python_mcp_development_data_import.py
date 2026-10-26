"""The isolated fork may import only pinned, non-PIT development data."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from application.python_mcp_development_data import import_pinned_development_data
from core.data.contracts import Bar, DataZone, MarketDataSet
from core.data.parquet import ParquetDataProvider


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "original"
    source.mkdir()
    bars = (
        Bar(datetime(2020, 1, 2, tzinfo=timezone.utc), "QQQ", 100, 102, 99, 101, 1000),
        Bar(datetime(2020, 1, 3, tzinfo=timezone.utc), "QQQ", 102, 103, 100, 101, 900),
    )
    data = MarketDataSet("v1", DataZone.DEVELOPMENT, bars)
    path = source / "QQQ_2020-01-02_2020-01-03_raw.parquet"
    ParquetDataProvider.write(path, data)
    manifest = {
        "classification": "NON_PIT_DEVELOPMENT_ONLY",
        "orders_enabled": False,
        "parquet_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dataset_hash": data.dataset_hash,
        "bars": 2,
        "start": "2020-01-02",
        "end": "2020-01-03",
    }
    (source / "snapshot-origin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path, source / "snapshot-origin.json"


def test_verified_copy_is_isolated_and_idempotent(tmp_path: Path):
    source, manifest = _fixture(tmp_path)
    root = tmp_path / "fork"
    root.mkdir()
    first = import_pinned_development_data(root, source, manifest)
    second = import_pinned_development_data(root, source, manifest)
    assert first == second
    assert first["status"] == "VERIFIED_EXISTING_DEVELOPMENT_COPY"
    assert first["bars"] == 2
    assert first["point_in_time_verified"] is False
    copied = root / first["data_path"]
    assert copied.is_file() and not copied.is_symlink()
    assert copied.read_bytes() == source.read_bytes()
    assert not (root / "data").exists()


def test_wrong_manifest_hash_rejected_without_copy(tmp_path: Path):
    source, manifest_path = _fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["parquet_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    root = tmp_path / "fork"
    root.mkdir()
    with pytest.raises(ValueError, match="sha256"):
        import_pinned_development_data(root, source, manifest_path)
    assert not (root / "state").exists()


@pytest.mark.parametrize("field,value", [
    ("classification", "SEALED_OOS"),
    ("orders_enabled", True),
])
def test_unsafe_manifest_rejected(tmp_path: Path, field: str, value: object):
    source, manifest_path = _fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    root = tmp_path / "fork"
    root.mkdir()
    with pytest.raises(ValueError):
        import_pinned_development_data(root, source, manifest_path)


def test_existing_different_bytes_not_overwritten(tmp_path: Path):
    source, manifest = _fixture(tmp_path)
    root = tmp_path / "fork"
    root.mkdir()
    dest = root / "state/python-mcp/development-qqq" / source.name
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"different")
    with pytest.raises(ValueError, match="overwrite"):
        import_pinned_development_data(root, source, manifest)
    assert dest.read_bytes() == b"different"


def test_symlink_destination_rejected_without_touching_target(tmp_path: Path):
    source, manifest = _fixture(tmp_path)
    root = tmp_path / 'fork'
    root.mkdir()
    outside = tmp_path / 'elsewhere'
    outside.mkdir()
    (root / 'state').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='destination research path'):
        import_pinned_development_data(root, source, manifest)
    assert list(outside.iterdir()) == []


def test_sealed_parquet_rejected_despite_development_manifest(tmp_path: Path):
    source, manifest_path = _fixture(tmp_path)
    data = ParquetDataProvider.read(source)
    from dataclasses import replace

    ParquetDataProvider.write(source, replace(data, zone=DataZone.SEALED_OOS))
    manifest = json.loads(manifest_path.read_text())
    manifest['parquet_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest['dataset_hash'] = ParquetDataProvider.read(source).dataset_hash
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    root = tmp_path / 'fork'
    root.mkdir()
    with pytest.raises(ValueError, match='sealed'):
        import_pinned_development_data(root, source, manifest_path)
    assert not (root / 'state').exists()
