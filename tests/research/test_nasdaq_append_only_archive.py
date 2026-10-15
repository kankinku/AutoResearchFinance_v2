"""Append-only real-source capture storage can be replayed; never historical PIT."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_append_only_archive import (
    archive_nasdaq_qqq_snapshot,
)
from research.indicator_engine.verified_capture_vintages import (
    CapturedPriceVintage,
    compare_verified_nasdaq_vintages,
)

START, END = date(2020, 1, 2), date(2020, 1, 3)
T0 = datetime(2026, 10, 15, 11, 9, 47, 123456, tzinfo=timezone.utc)


def _payload(close: str = "211.8") -> bytes:
    return json.dumps({
        "data": {"symbol": "QQQ", "totalRecords": 2, "tradesTable": {"rows": [
            {"date": "01/03/2020", "open": "211", "high": "212", "low": "210",
             "close": close, "volume": "2,000"},
            {"date": "01/02/2020", "open": "210", "high": "212", "low": "209",
             "close": "211", "volume": "1,000"},
        ], "asOf": None}}, "status": {"rCode": 200}
    }).encode()


def test_first_and_later_snapshots_distinct_replayable_and_non_pit(tmp_path: Path):
    root = tmp_path / "ignored-local-archive"
    first = archive_nasdaq_qqq_snapshot(
        root, START, END, at=T0, fetch_bytes=lambda _: _payload()
    )
    second = archive_nasdaq_qqq_snapshot(
        root, START, END, at=T0 + timedelta(days=1),
        fetch_bytes=lambda _: _payload("211.9"),
    )
    for item in (first, second):
        assert item.verified_rows == 2
        assert item.integrity_status == "LOCAL_CAPTURE_BYTES_VERIFIED"
        assert item.point_in_time_verified is False
        assert item.broker_executable is False
        assert item.raw_sha256
        assert item.captured_at.endswith("+00:00")
        assert item.capture_hash
        assert item.directory.is_dir()
        assert item.manifest_path.is_file()
        assert item.raw_path.is_file()
        assert item.parquet_path.is_file()
        if os.name != "nt":
            assert item.directory.stat().st_mode & 0o777 == 0o700
            for f in (item.raw_path, item.parquet_path, item.manifest_path):
                assert f.stat().st_mode & 0o777 == 0o600
    compared = compare_verified_nasdaq_vintages(
        CapturedPriceVintage(first.parquet_path, first.raw_path, first.manifest_path),
        CapturedPriceVintage(second.parquet_path, second.raw_path, second.manifest_path),
    )
    assert compared.status == "HISTORICAL_ROWS_REVISED"
    assert compared.changed_session_dates == ("2020-01-03",)


def test_cannot_overwrite_archive_even_if_same_source_data(tmp_path: Path):
    archive_nasdaq_qqq_snapshot(
        tmp_path, START, END, at=T0, fetch_bytes=lambda _: _payload()
    )
    with pytest.raises(ResearchCatalogError, match="exists"):
        archive_nasdaq_qqq_snapshot(
            tmp_path, START, END, at=T0, fetch_bytes=lambda _: _payload()
        )
    assert len(list(tmp_path.iterdir())) == 1


def test_broken_remote_fetch_leaves_no_false_manifest_or_dataset(tmp_path: Path):
    def fail(_: str) -> bytes:
        raise OSError("network blocked")
    with pytest.raises(ResearchCatalogError, match="fetch"):
        archive_nasdaq_qqq_snapshot(
            tmp_path, START, END, at=T0, fetch_bytes=fail
        )
    assert list(tmp_path.iterdir()) == []


def test_invalid_timestamps_and_forged_payload_fail_closed(tmp_path: Path):
    with pytest.raises(ResearchCatalogError, match="timezone"):
        archive_nasdaq_qqq_snapshot(
            tmp_path, START, END, at=datetime(2026, 10, 15),
            fetch_bytes=lambda _: _payload()
        )
    with pytest.raises(ResearchCatalogError):
        archive_nasdaq_qqq_snapshot(
            tmp_path, START, END, at=T0, fetch_bytes=lambda _: b"not-json"
        )
    assert list(tmp_path.iterdir()) == []



def test_archival_cli_writes_new_replayable_snapshot(tmp_path: Path, monkeypatch, capsys):
    import sys
    from functools import partial

    from research.indicator_engine import cli
    from research.indicator_engine.nasdaq_append_only_archive import (
        archive_nasdaq_qqq_snapshot as capture,
    )

    monkeypatch.setattr(
        cli, "archive_nasdaq_qqq_snapshot",
        partial(capture, at=T0, fetch_bytes=lambda _: _payload()),
    )
    monkeypatch.setattr(sys, "argv", [
        "research-cli", "archive-nasdaq-qqq",
        "--from-date", START.isoformat(),
        "--to-date", END.isoformat(),
        "--archive-root", str(tmp_path),
    ])
    assert cli.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["verified_rows"] == 2
    assert report["integrity_status"] == "LOCAL_CAPTURE_BYTES_VERIFIED"
    assert report["point_in_time_verified"] is False
    assert Path(report["manifest_path"]).exists()
    assert cli.main() == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["status"] == "ARCHIVE_CAPTURE_FAILED"
    assert failure["broker_executable"] is False



def test_existing_nonprivate_archive_root_refused_without_chmod(tmp_path: Path):
    if os.name == "nt":
        pytest.skip("POSIX permissions only")
    insecure = tmp_path / "existing"
    insecure.mkdir(mode=0o755)
    insecure.chmod(0o755)
    with pytest.raises(ResearchCatalogError, match="private"):
        archive_nasdaq_qqq_snapshot(
            insecure, START, END, at=T0, fetch_bytes=lambda _: _payload()
        )
    assert insecure.stat().st_mode & 0o777 == 0o755
    assert list(insecure.iterdir()) == []
