"""External publisher signature != trusted historical PIT release timestamps."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from research.indicator_engine import publisher_evidence_intake as evidence
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_capture import capture_nasdaq_qqq
from research.indicator_engine.verified_capture_vintages import CapturedPriceVintage


def _raw() -> bytes:
    return json.dumps({
        "data": {"symbol": "QQQ", "totalRecords": 2, "tradesTable": {"rows": [
            {"date": "01/03/2020", "open": "211", "high": "212", "low": "210",
             "close": "211.8", "volume": "2,000"},
            {"date": "01/02/2020", "open": "210", "high": "212", "low": "209",
             "close": "211", "volume": "1,000"},
        ], "asOf": None}}, "status": {"rCode": 200}
    }).encode()


def _capture(tmp_path: Path) -> CapturedPriceVintage:
    out = tmp_path / "qqq.parquet"
    raw = tmp_path / "qqq.raw.json"
    proof = tmp_path / "qqq.manifest.json"
    capture_nasdaq_qqq(
        date(2020, 1, 2), date(2020, 1, 3), out, raw, proof,
        fetch_bytes=lambda _: _raw(),
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    return CapturedPriceVintage(out, raw, proof)


def _signed(
    tmp_path: Path, signer: Ed25519PrivateKey, **replacements: str,
) -> tuple[Path, Path]:
    item = {
        "schema": "nasdaq-publisher-content-proof-v1",
        "provider_id": "nasdaq-public",
        "publisher_key_id": "unit-only",
        "raw_sha256": hashlib.sha256(_raw()).hexdigest(),
        "coverage_start": "2020-01-02",
        "coverage_end": "2020-01-03",
        "asserted_published_at": "2020-01-04T22:00:00+00:00",
    }
    item.update(replacements)
    body = json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
    proof = tmp_path / "publisher-attestation.json"
    signature = tmp_path / "publisher-attestation.sig"
    proof.write_bytes(body)
    signature.write_bytes(signer.sign(body))
    return proof, signature


def _pin(monkeypatch: pytest.MonkeyPatch, signer: Ed25519PrivateKey) -> None:
    pub = signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setattr(
        evidence, "TRUSTED_PUBLISHER_PUBLIC_KEYS",
        MappingProxyType({("nasdaq-public", "unit-only"): pub}),
    )


def test_existing_real_style_local_capture_has_no_independent_publication_evidence(
    tmp_path: Path,
):
    result = evidence.audit_publisher_evidence(_capture(tmp_path))
    assert result.status == "PUBLISHER_PROOF_MISSING"
    assert result.local_capture_replay_verified
    assert result.publisher_signature_verified is False
    assert result.publisher_available_at_proven is False
    assert result.independent_historical_pit_verified is False
    assert result.broker_executable is False
    assert "independent_publisher_proof_missing" in result.blocking_reasons


def test_untrusted_self_signed_proof_never_approved(tmp_path: Path):
    capture = _capture(tmp_path)
    private = Ed25519PrivateKey.generate()
    proof, signature = _signed(tmp_path, private)
    checked = evidence.audit_publisher_evidence(capture, proof, signature)
    assert checked.status == "UNTRUSTED_PUBLISHER_KEY"
    assert checked.publisher_signature_verified is False
    assert checked.independent_historical_pit_verified is False


def test_synthetic_pinned_signature_verifies_content_but_not_publication_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    capture = _capture(tmp_path)
    private = Ed25519PrivateKey.generate()
    _pin(monkeypatch, private)
    proof, signature = _signed(tmp_path, private)
    checked = evidence.audit_publisher_evidence(capture, proof, signature)
    assert checked.status == "SIGNED_CONTENT_UNTIMESTAMPED"
    assert checked.publisher_signature_verified is True
    assert checked.publisher_available_at_proven is False
    assert checked.independent_historical_pit_verified is False
    assert checked.broker_executable is False


@pytest.mark.parametrize(
    "tamper", ["wrong_hash", "wrong_scope", "modified_body", "wrong_signature"]
)
def test_wrong_content_or_invalid_signature_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str,
):
    capture = _capture(tmp_path)
    private = Ed25519PrivateKey.generate()
    _pin(monkeypatch, private)
    extra = {}
    if tamper == "wrong_hash":
        extra["raw_sha256"] = "0" * 64
    elif tamper == "wrong_scope":
        extra["coverage_end"] = "2020-01-04"
    proof, signature = _signed(tmp_path, private, **extra)
    if tamper == "modified_body":
        proof.write_bytes(proof.read_bytes().replace(b"unit-only", b"other-key"))
    elif tamper == "wrong_signature":
        signature.write_bytes(Ed25519PrivateKey.generate().sign(proof.read_bytes()))
    checked = evidence.audit_publisher_evidence(capture, proof, signature)
    assert checked.publisher_signature_verified is False or (
        checked.status in {"SOURCE_DIGEST_MISMATCH", "SOURCE_SCOPE_MISMATCH"}
    )
    assert checked.independent_historical_pit_verified is False
    assert checked.status != "SIGNED_CONTENT_UNTIMESTAMPED"


def test_declared_early_release_does_not_override_late_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    capture = _capture(tmp_path)
    private = Ed25519PrivateKey.generate()
    _pin(monkeypatch, private)
    proof, signature = _signed(tmp_path, private)
    checked = evidence.audit_publisher_evidence(
        capture, proof, signature,
        decision_at=datetime(2020, 1, 5, tzinfo=timezone.utc),
    )
    assert checked.status == "HISTORICAL_CAPTURE_TOO_LATE"
    assert "local_snapshot_captured_after_decision" in checked.blocking_reasons
    assert checked.independent_historical_pit_verified is False


def test_partial_files_fail_closed_and_bad_timestamps_rejected(tmp_path: Path):
    capture = _capture(tmp_path)
    with pytest.raises(ResearchCatalogError, match="pair"):
        evidence.audit_publisher_evidence(capture, tmp_path / "missing", None)
    with pytest.raises(ValueError, match="timezone"):
        evidence.audit_publisher_evidence(
            capture, decision_at=datetime(2020, 1, 5),
        )


def test_cli_local_proof_intake_reports_missing_proof_without_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
):
    import sys

    from research.indicator_engine.cli import main

    capture = _capture(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "research-cli", "audit-publisher-evidence",
        "--output", str(capture.parquet_path),
        "--raw", str(capture.raw_path),
        "--manifest", str(capture.manifest_path),
    ])
    assert main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "PUBLISHER_PROOF_MISSING"
    assert out["local_capture_replay_verified"] is True
    assert out["publisher_available_at_proven"] is False
