"""Offline two-vintage Nasdaq capture verification (no historical PIT promotion)."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_capture import capture_nasdaq_qqq
from research.indicator_engine.verified_capture_vintages import (
    CapturedPriceVintage,
    compare_verified_nasdaq_vintages,
)

_START, _END = date(2020, 1, 2), date(2020, 1, 3)


def _raw(second_close: str = "211.8") -> bytes:
    return json.dumps({
        "data": {"symbol": "QQQ", "totalRecords": 2, "tradesTable": {"rows": [
            {"date": "01/03/2020", "open": "211", "high": "212", "low": "210",
             "close": second_close, "volume": "2,000"},
            {"date": "01/02/2020", "open": "210", "high": "212", "low": "209",
             "close": "211", "volume": "1,000"},
        ], "asOf": None}}, "status": {"rCode": 200}
    }).encode()


def _capture(root: Path, name: str, stamp: datetime, close: str = "211.8"):
    folder = root / name
    output = folder / "qqq.parquet"
    raw = folder / "qqq.raw.json"
    proof = folder / "qqq.manifest.json"
    capture_nasdaq_qqq(
        _START, _END, output, raw, proof,
        captured_at=stamp, fetch_bytes=lambda url: _raw(close),
    )
    return CapturedPriceVintage(parquet_path=output, raw_path=raw, manifest_path=proof)


def test_valid_two_captures_detect_revised_older_session_but_not_pit(tmp_path: Path):
    older = _capture(tmp_path, "first", datetime(2026, 10, 10, tzinfo=timezone.utc))
    newer = _capture(tmp_path, "second", datetime(2026, 10, 15, tzinfo=timezone.utc),
                     "211.9")
    result = compare_verified_nasdaq_vintages(older, newer)
    assert result.status == "HISTORICAL_ROWS_REVISED"
    assert result.comparable_bars == 2
    assert result.changed_bars == 1
    assert result.changed_session_dates == ("2020-01-03",)
    assert result.earlier_raw_sha256 != result.later_raw_sha256
    assert result.pair_hash
    assert result.point_in_time_price_verified is False
    assert result.independent_historical_publication_verified is False
    assert result.broker_executable is False
    assert result.record()["independence"] == "SAME_PROVIDER_LOCAL_CAPTURE_TIMES"


def test_matching_captures_are_not_an_independent_pit_vintage(tmp_path: Path):
    older = _capture(tmp_path, "first", datetime(2026, 10, 10, tzinfo=timezone.utc))
    newer = _capture(tmp_path, "second", datetime(2026, 10, 15, tzinfo=timezone.utc))
    result = compare_verified_nasdaq_vintages(older, newer)
    assert result.status == "OVERLAPPING_ROWS_UNCHANGED"
    assert result.changed_bars == 0
    assert result.comparable_bars == 2
    assert not result.point_in_time_price_verified


@pytest.mark.parametrize("order", ["swapped", "same_time"])
def test_collection_timestamps_must_increase(tmp_path: Path, order: str):
    first_stamp = datetime(2026, 10, 10, tzinfo=timezone.utc)
    older = _capture(tmp_path, "first", first_stamp)
    newer = _capture(
        tmp_path, "second",
        first_stamp if order == "same_time" else datetime(2026, 10, 15, tzinfo=timezone.utc)
    )
    if order == "swapped":
        older, newer = newer, older
    with pytest.raises(ResearchCatalogError, match="chronological"):
        compare_verified_nasdaq_vintages(older, newer)


@pytest.mark.parametrize("part", ["raw", "manifest", "parquet"])
def test_mismatched_or_tampered_capture_refuses_comparison(tmp_path: Path, part: str):
    older = _capture(tmp_path, "first", datetime(2026, 10, 10, tzinfo=timezone.utc))
    newer = _capture(tmp_path, "second", datetime(2026, 10, 15, tzinfo=timezone.utc))
    target = {
        "raw": newer.raw_path,
        "manifest": newer.manifest_path,
        "parquet": newer.parquet_path,
    }[part]
    target.write_bytes(b"tampered")
    with pytest.raises(ResearchCatalogError):
        compare_verified_nasdaq_vintages(older, newer)


def test_same_snapshot_pair_is_refused(tmp_path: Path):
    source = _capture(tmp_path, "first", datetime(2026, 10, 10, tzinfo=timezone.utc))
    with pytest.raises(ResearchCatalogError, match="distinct"):
        compare_verified_nasdaq_vintages(source, source)



def test_offline_cli_compares_capture_pair_without_pit_claim(
    tmp_path: Path, monkeypatch, capsys,
):
    import sys

    from research.indicator_engine.cli import main

    a = _capture(tmp_path, "first", datetime(2026, 10, 10, tzinfo=timezone.utc))
    b = _capture(tmp_path, "second", datetime(2026, 10, 15, tzinfo=timezone.utc),
                 "211.9")
    argv = [
        "research-cli", "compare-nasdaq-vintages",
        "--earlier-output", str(a.parquet_path),
        "--earlier-raw", str(a.raw_path),
        "--earlier-manifest", str(a.manifest_path),
        "--later-output", str(b.parquet_path),
        "--later-raw", str(b.raw_path),
        "--later-manifest", str(b.manifest_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "HISTORICAL_ROWS_REVISED"
    assert report["changed_bars"] == 1
    assert report["independent_historical_publication_verified"] is False
    assert report["broker_executable"] is False
    b.raw_path.write_bytes(b"tampered")
    assert main() == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["status"] == "CAPTURE_VINTAGE_PAIR_INVALID"
    assert failure["point_in_time_price_verified"] is False
