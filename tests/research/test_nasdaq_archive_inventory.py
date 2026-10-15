"""Audit real-source QQQ archival sequence without mislabelling historical PIT."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_append_only_archive import archive_nasdaq_qqq_snapshot
from research.indicator_engine.nasdaq_archive_inventory import audit_nasdaq_qqq_archive
from research.indicator_engine.nasdaq_capture import capture_nasdaq_qqq

START, END = date(2020, 1, 2), date(2020, 1, 3)
BASE = (
    datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
    - timedelta(days=4)
)


def _payload(close: str = "211.8") -> bytes:
    return json.dumps({
        "data": {"symbol": "QQQ", "totalRecords": 2, "tradesTable": {"rows": [
            {"date": "01/03/2020", "open": "211", "high": "212", "low": "210",
             "close": close, "volume": "2,000"},
            {"date": "01/02/2020", "open": "210", "high": "212", "low": "209",
             "close": "211", "volume": "1,000"},
        ], "asOf": None}}, "status": {"rCode": 200}
    }).encode()


def _capture(root: Path, stamp: datetime, close: str = "211.8"):
    return archive_nasdaq_qqq_snapshot(
        root, START, END, at=stamp, fetch_bytes=lambda _: _payload(close),
    )


def test_two_same_day_real_style_captures_are_not_longitudinal(tmp_path: Path):
    _capture(tmp_path, BASE)
    _capture(tmp_path, BASE + timedelta(minutes=7))
    report = audit_nasdaq_qqq_archive(tmp_path, START, END)
    assert report.status == "INSUFFICIENT_COLLECTION_DAYS"
    assert report.capture_count == 2
    assert report.distinct_collection_days == 1
    assert report.verified_capture_count == 2
    assert report.compared_consecutive_pairs == 1
    assert report.total_revised_bars == 0
    assert report.missing_collection_dates == ()
    assert report.point_in_time_verified is False
    assert report.broker_executable is False
    assert report.record()["independent_historical_publication_verified"] is False
    assert report.record()["captured_raw_bytes_exported"] is False


def test_different_dates_with_adjacent_collection_days_are_stable(tmp_path: Path):
    _capture(tmp_path, BASE)
    _capture(tmp_path, BASE + timedelta(days=1))
    report = audit_nasdaq_qqq_archive(tmp_path, START, END)
    assert report.status == "OBSERVED_COLLECTION_SEQUENCE_STABLE"
    assert report.distinct_collection_days == 2
    assert report.missing_collection_dates == ()
    assert report.total_revised_bars == 0
    assert not report.point_in_time_verified


def test_gap_in_collection_dates_and_revisions_are_separately_reported(tmp_path: Path):
    _capture(tmp_path, BASE)
    _capture(tmp_path, BASE + timedelta(days=3), "211.9")
    report = audit_nasdaq_qqq_archive(tmp_path, START, END)
    assert report.status == "COLLECTION_DATE_GAPS"
    assert report.missing_collection_dates == (
        (BASE + timedelta(days=1)).date().isoformat(),
        (BASE + timedelta(days=2)).date().isoformat(),
    )
    assert report.total_revised_bars == 1
    assert report.revised_date_examples == ("2020-01-03",)
    assert report.compared_consecutive_pairs == 1


def test_one_real_style_legacy_flat_capture_and_archive_folder(tmp_path: Path):
    first = tmp_path / "qqq_archive_legacy"
    capture_nasdaq_qqq(
        START, END,
        first.with_suffix(".parquet"),
        tmp_path / "qqq_archive_legacy.raw.json",
        tmp_path / "qqq_archive_legacy.manifest.json",
        captured_at=BASE, fetch_bytes=lambda _: _payload(),
    )
    for suffix in (".parquet", ".raw.json", ".manifest.json"):
        (tmp_path / ("qqq_archive_legacy" + suffix)).chmod(0o600)
    _capture(tmp_path, BASE + timedelta(days=1))
    report = audit_nasdaq_qqq_archive(tmp_path, START, END)
    assert report.capture_count == 2
    assert report.status == "OBSERVED_COLLECTION_SEQUENCE_STABLE"


def test_tamper_or_half_written_capture_fails_closed(tmp_path: Path):
    item = _capture(tmp_path, BASE)
    item.raw_path.write_bytes(item.raw_path.read_bytes() + b"forged")
    with pytest.raises(ResearchCatalogError):
        audit_nasdaq_qqq_archive(tmp_path, START, END)
    item.raw_path.write_bytes(_payload())
    item.manifest_path.unlink()
    with pytest.raises(ResearchCatalogError, match="missing"):
        audit_nasdaq_qqq_archive(tmp_path, START, END)


def test_mixed_collection_periods_and_out_of_scope_captures_refused(tmp_path: Path):
    _capture(tmp_path, BASE)
    archive_nasdaq_qqq_snapshot(
        tmp_path, date(2020, 1, 1), date(2020, 1, 3),
        at=BASE + timedelta(days=1), fetch_bytes=lambda _: _payload(),
    )
    with pytest.raises(ResearchCatalogError, match="scope"):
        audit_nasdaq_qqq_archive(tmp_path, START, END)


def test_symlink_and_open_permissions_refused(tmp_path: Path):
    if os.name == "nt":
        pytest.skip("POSIX enforcement")
    item = _capture(tmp_path, BASE)
    item.raw_path.rename(item.raw_path.with_suffix(".backup"))
    item.raw_path.symlink_to(item.raw_path.with_suffix(".backup"))
    with pytest.raises(ResearchCatalogError, match="symlink"):
        audit_nasdaq_qqq_archive(tmp_path, START, END)
    item.raw_path.unlink()
    item.raw_path.with_suffix(".backup").rename(item.raw_path)
    tmp_path.chmod(0o755)
    with pytest.raises(ResearchCatalogError, match="private"):
        audit_nasdaq_qqq_archive(tmp_path, START, END)


def test_empty_archive_does_not_pass(tmp_path: Path):
    result = audit_nasdaq_qqq_archive(tmp_path, START, END)
    assert result.status == "NO_CAPTURES"
    assert result.capture_count == 0
    assert result.point_in_time_verified is False


def test_offline_cli_reports_same_day_insufficiency(tmp_path: Path, monkeypatch, capsys):
    import sys

    from research.indicator_engine.cli import main

    _capture(tmp_path, BASE)
    _capture(tmp_path, BASE + timedelta(minutes=10))
    monkeypatch.setattr(sys, "argv", [
        "research-cli", "audit-nasdaq-archive",
        "--from-date", START.isoformat(), "--to-date", END.isoformat(),
        "--archive-root", str(tmp_path),
    ])
    assert main() == 0
    record = json.loads(capsys.readouterr().out)
    assert record["status"] == "INSUFFICIENT_COLLECTION_DAYS"
    assert record["capture_count"] == 2
    assert record["point_in_time_verified"] is False
