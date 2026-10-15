"""Idempotent daily QQQ source capture: integrity first, never historical PIT."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from functools import partial
from pathlib import Path

import pytest

from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_append_only_archive import archive_nasdaq_qqq_snapshot
from research.indicator_engine.nasdaq_archive_inventory import audit_nasdaq_qqq_archive
from research.indicator_engine.nasdaq_daily_collector import collect_nasdaq_qqq_daily

START, END = date(2020, 1, 2), date(2020, 1, 3)
T0 = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(
    days=4
)


def _payload(close: str = "211.8") -> bytes:
    return json.dumps(
        {
            "data": {
                "symbol": "QQQ",
                "totalRecords": 2,
                "tradesTable": {
                    "rows": [
                        {
                            "date": "01/03/2020",
                            "open": "211",
                            "high": "212",
                            "low": "210",
                            "close": close,
                            "volume": "2,000",
                        },
                        {
                            "date": "01/02/2020",
                            "open": "210",
                            "high": "212",
                            "low": "209",
                            "close": "211",
                            "volume": "1,000",
                        },
                    ],
                    "asOf": None,
                },
            },
            "status": {"rCode": 200},
        }
    ).encode()


def test_daily_capture_is_idempotent_and_does_not_fetch_twice(tmp_path: Path) -> None:
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return _payload()

    first = collect_nasdaq_qqq_daily(tmp_path / "archive", START, END, at=T0, fetch_bytes=fetch)
    again = collect_nasdaq_qqq_daily(
        tmp_path / "archive", START, END, at=T0 + timedelta(hours=3), fetch_bytes=fetch
    )
    assert first["status"] == "NEW_CAPTURE_VERIFIED"
    assert again["status"] == "ALREADY_COLLECTED_TODAY"
    assert first["inventory"]["capture_count"] == 1
    assert again["inventory"]["capture_count"] == 1
    assert len(calls) == 1
    assert not first["point_in_time_verified"]
    assert not again["broker_executable"]


def test_different_utc_day_appends_and_audits_revisions(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    one = collect_nasdaq_qqq_daily(root, START, END, at=T0, fetch_bytes=lambda _: _payload())
    two = collect_nasdaq_qqq_daily(
        root,
        START,
        END,
        at=T0 + timedelta(days=1),
        fetch_bytes=lambda _: _payload("211.9"),
    )
    report = audit_nasdaq_qqq_archive(root, START, END)
    assert one["status"] == two["status"] == "NEW_CAPTURE_VERIFIED"
    assert report.capture_count == 2
    assert report.distinct_collection_days == 2
    assert report.total_revised_bars == 1
    assert report.status == "OBSERVED_REVISIONS"
    assert one["receipt"]["raw_sha256"] != two["receipt"]["raw_sha256"]
    assert not two["point_in_time_verified"]


def test_existing_manual_capture_is_skipped_and_tamper_blocks_fetch(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    first = archive_nasdaq_qqq_snapshot(root, START, END, at=T0, fetch_bytes=lambda _: _payload())

    def forbidden(_url: str) -> bytes:
        pytest.fail("same-day capture or failed integrity check must not fetch")

    skipped = collect_nasdaq_qqq_daily(
        root, START, END, at=T0 + timedelta(minutes=1), fetch_bytes=forbidden
    )
    assert skipped["status"] == "ALREADY_COLLECTED_TODAY"
    first.raw_path.write_bytes(b"corrupt")
    with pytest.raises(ResearchCatalogError):
        collect_nasdaq_qqq_daily(root, START, END, at=T0 + timedelta(days=1), fetch_bytes=forbidden)
    assert len(list(root.glob("qqq_*/"))) == 1


def test_symlink_root_fails_closed(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX symlink check")
    actual = tmp_path / "real"
    actual.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ResearchCatalogError, match="symlink"):
        collect_nasdaq_qqq_daily(link, START, END, at=T0, fetch_bytes=lambda _: _payload())
    assert list(actual.iterdir()) == []


def test_daily_cli_reports_skipped_without_fetch(tmp_path: Path, monkeypatch, capsys) -> None:
    from research.indicator_engine import cli

    root = tmp_path / "archive"
    monkeypatch.setattr(
        cli,
        "collect_nasdaq_qqq_daily",
        partial(collect_nasdaq_qqq_daily, at=T0, fetch_bytes=lambda _: _payload()),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "research-cli",
            "collect-nasdaq-qqq-daily",
            "--from-date",
            START.isoformat(),
            "--to-date",
            END.isoformat(),
            "--archive-root",
            str(root),
        ],
    )
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "NEW_CAPTURE_VERIFIED"
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ALREADY_COLLECTED_TODAY"
