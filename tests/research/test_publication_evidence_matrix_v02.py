"""V02 publication evidence chain: retained source != historical availability."""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from research.indicator_engine import cli
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_append_only_archive import archive_nasdaq_qqq_snapshot
from research.indicator_engine.publication_evidence_matrix import audit_publication_coverage
from tests.research.test_nasdaq_archive_inventory import BASE, END, START, _payload


def _one(root: Path, *, offset: int = 0):
    return archive_nasdaq_qqq_snapshot(
        root, START, END, at=BASE + timedelta(days=offset),
        fetch_bytes=lambda _url: _payload(),
    )


def test_real_style_two_day_archives_do_not_prove_publication(tmp_path: Path) -> None:
    first = _one(tmp_path)
    second = _one(tmp_path, offset=1)
    before = audit_publication_coverage(tmp_path, START, END)
    assert before["source_capture_count"] == 2
    assert before["verified_local_source_count"] == 2
    assert before["historical_publication_attested_captures"] == 0
    assert before["publisher_proof_status_counts"] == {"PUBLISHER_PROOF_MISSING": 2}
    assert before["status"] == "INDEPENDENT_HISTORICAL_PUBLICATION_PROOF_MISSING"
    assert before["point_in_time_verified"] is False
    assert before["independent_oos_approved"] is False
    assert before["broker_executable"] is False
    assert before == audit_publication_coverage(tmp_path, START, END)
    assert first.raw_path.read_bytes() == second.raw_path.read_bytes()


def test_historical_decision_before_collection_fails_even_without_proof(
    tmp_path: Path,
) -> None:
    _one(tmp_path)
    result = audit_publication_coverage(
        tmp_path, START, END, decision_at=BASE - timedelta(days=30),
    )
    assert result["status"] == "HISTORICAL_CAPTURE_AFTER_DECISION_BLOCKED"
    assert result["capture_after_decision_count"] == 1
    assert result["captures"][0]["local_capture_after_decision"] is True
    assert result["captures"][0]["historical_pit_verified"] is False


def test_bad_utc_boundary_and_partial_evidence_refused(tmp_path: Path) -> None:
    capture = _one(tmp_path)
    with pytest.raises(ResearchCatalogError, match="timezone"):
        audit_publication_coverage(
            tmp_path, START, END, decision_at=BASE.replace(tzinfo=None),
        )
    attached = capture.manifest_path.parent / "qqq.publisher-claim.json"
    attached.write_text("{}", encoding="utf-8")
    with pytest.raises(ResearchCatalogError, match="pair"):
        audit_publication_coverage(tmp_path, START, END)


def test_untrusted_self_claim_cannot_promote_pit(tmp_path: Path) -> None:
    capture = _one(tmp_path)
    folder = capture.manifest_path.parent
    claimed = folder / "qqq.publisher-claim.json"
    signature = folder / "qqq.publisher-claim.sig"
    body = {
        "schema": "nasdaq-publisher-content-proof-v1",
        "provider_id": "nasdaq-public",
        "publisher_key_id": "user-provided-not-trusted",
        "raw_sha256": capture.raw_sha256,
        "coverage_start": START.isoformat(),
        "coverage_end": END.isoformat(),
        "asserted_published_at": "2020-01-04T00:00:00+00:00",
    }
    claimed.write_bytes(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
    signature.write_bytes(b"x" * 64)
    result = audit_publication_coverage(tmp_path, START, END)
    assert result["status"] == "UNTRUSTED_OR_INVALID_PUBLISHER_PROOF"
    assert result["publisher_proof_status_counts"] == {"UNTRUSTED_PUBLISHER_KEY": 1}
    assert result["historical_publication_attested_captures"] == 0
    assert result["captures"][0]["publisher_signature_verified"] is False


def test_raw_tampering_refuses_whole_coverage_report(tmp_path: Path) -> None:
    capture = _one(tmp_path)
    _one(tmp_path, offset=1)
    capture.raw_path.write_bytes(capture.raw_path.read_bytes() + b"tamper")
    with pytest.raises(ResearchCatalogError):
        audit_publication_coverage(tmp_path, START, END)


def test_empty_archive_and_cli_safety(tmp_path: Path, monkeypatch, capsys) -> None:
    report = audit_publication_coverage(tmp_path, START, END)
    assert report["status"] == "NO_ARCHIVED_SOURCE"
    assert report["source_capture_count"] == 0
    _one(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "indicator-research", "audit-qqq-publication-coverage",
        "--archive-root", str(tmp_path),
        "--from-date", START.isoformat(), "--to-date", END.isoformat(),
    ])
    assert cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["source_capture_count"] == 1
    assert body["publisher_proof_status_counts"]["PUBLISHER_PROOF_MISSING"] == 1
    assert body["point_in_time_verified"] is False
    assert body["broker_executable"] is False


def test_cli_refuses_corrupted_raw_and_does_not_leak_claim(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    capture = _one(tmp_path)
    capture.raw_path.write_bytes(b"BAD MANIFEST SECRET")
    monkeypatch.setattr(sys, "argv", [
        "indicator-research", "audit-qqq-publication-coverage",
        "--archive-root", str(tmp_path),
        "--from-date", START.isoformat(), "--to-date", END.isoformat(),
    ])
    assert cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "PUBLICATION_COVERAGE_INTEGRITY_FAILED"
    assert body["broker_executable"] is False
    assert "BAD MANIFEST SECRET" not in json.dumps(body)
