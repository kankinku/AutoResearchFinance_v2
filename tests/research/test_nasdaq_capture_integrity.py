"""Archived Nasdaq snapshots must be reproducible, not trusted PIT vintages."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from research.indicator_engine.capture_integrity import verify_nasdaq_capture
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_capture import capture_nasdaq_qqq

_START, _END = date(2020, 1, 2), date(2020, 1, 3)
_AT = datetime(2026, 10, 14, 4, 30, tzinfo=timezone.utc)


def _bytes() -> bytes:
    return json.dumps({
        "data": {"symbol": "QQQ", "totalRecords": 2, "tradesTable": {"rows": [
            {"date":"01/03/2020", "open":"211", "high":"212", "low":"210",
             "close":"211.8", "volume":"2,000"},
            {"date":"01/02/2020", "open":"210", "high":"212", "low":"209",
             "close":"211", "volume":"1,000"},
        ],"asOf":None}}, "status":{"rCode":200},
    }).encode()


def _capture(tmp_path: Path):
    output = tmp_path / "nasdaq.parquet"
    raw = tmp_path / "capture.raw.json"
    proof = tmp_path / "capture.manifest.json"
    capture_nasdaq_qqq(_START, _END, output, raw, proof,
                       fetch_bytes=lambda url: _bytes(), captured_at=_AT)
    return output, raw, proof


def test_immutable_capture_replays_and_remains_unapproved(tmp_path: Path):
    output, raw, proof = _capture(tmp_path)
    checked = verify_nasdaq_capture(output, raw, proof)
    assert checked.verified_rows == 2
    assert checked.status == "LOCAL_CAPTURE_BYTES_VERIFIED"
    assert not checked.point_in_time_verified
    assert not checked.independent_benchmark_verified
    assert not checked.candidate_promotable
    assert checked == verify_nasdaq_capture(output, raw, proof)


def test_refuses_tampered_raw_or_parquet(tmp_path: Path):
    output, raw, proof = _capture(tmp_path)
    raw.write_bytes(_bytes().replace(b'"211.8"', b'"211.9"'))
    with pytest.raises(ResearchCatalogError, match="raw digest"):
        verify_nasdaq_capture(output, raw, proof)
    raw.write_bytes(_bytes())
    output.write_bytes(b"forged-not-parquet")
    with pytest.raises(ResearchCatalogError, match="parquet"):
        verify_nasdaq_capture(output, raw, proof)


@pytest.mark.parametrize("field, forged", [
    ("point_in_time_verified", True),
    ("independent_benchmark_verified", True),
    ("candidate_promotable", True),
    ("source_url", "https://arbitrary.example/api/quote/QQQ/historical?assetclass=etf"),
    ("row_count", 9999),
    ("dataset_hash", "0" * 64),
    ("raw_path", "/tmp/other-secret-file"),
])
def test_refuses_mislabelled_or_swapped_manifest(tmp_path: Path, field: str, forged):
    output, raw, proof = _capture(tmp_path)
    manifest = json.loads(proof.read_text())
    manifest[field] = forged
    proof.write_text(json.dumps(manifest))
    with pytest.raises(ResearchCatalogError):
        verify_nasdaq_capture(output, raw, proof)


def test_offline_capture_verification_cli(tmp_path: Path, monkeypatch, capsys):
    import sys

    from research.indicator_engine.cli import main

    output, raw, proof = _capture(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "research-cli", "verify-nasdaq-capture", "--output", str(output),
        "--raw", str(raw), "--manifest", str(proof),
    ])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "LOCAL_CAPTURE_BYTES_VERIFIED"
    assert report["verified_rows"] == 2
    assert not report["point_in_time_verified"]
    raw.write_bytes(b"changed-bytes")
    assert main() == 2
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == "CAPTURE_INTEGRITY_FAILED"
