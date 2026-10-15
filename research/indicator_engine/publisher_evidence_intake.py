"""Read-only authenticated-content intake, never a historical PIT authorization.

Detached Ed25519 proof binds a publisher-signed *claim* to retained Nasdaq raw
bytes. Without independently verified vintage creation time and original
release/availability evidence this does NOT prove a past trader saw those bytes.

Production trust registry is deliberately empty: no publisher's genuine signing
key and historic availability feed have been independently onboarded.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from research.indicator_engine.capture_integrity import verify_nasdaq_capture
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.verified_capture_vintages import CapturedPriceVintage

# Trust-on-first-use and caller-selected public keys are deliberately forbidden.
# Actual reviewed provider identity, license, and key provenance must be pinned
# in a separate auditable onboarding change before any new key is added here.
TRUSTED_PUBLISHER_PUBLIC_KEYS: MappingProxyType[
    tuple[str, str], bytes
] = MappingProxyType({})

_EVIDENCE_KEYS = frozenset({
    "schema", "provider_id", "publisher_key_id", "raw_sha256",
    "coverage_start", "coverage_end", "asserted_published_at",
})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_EVIDENCE = 4096
Status = Literal[
    "PUBLISHER_PROOF_MISSING", "UNTRUSTED_PUBLISHER_KEY",
    "INVALID_PUBLISHER_EVIDENCE", "SOURCE_DIGEST_MISMATCH",
    "SOURCE_SCOPE_MISMATCH", "HISTORICAL_CAPTURE_TOO_LATE",
    "ASSERTED_PUBLICATION_AFTER_DECISION", "SIGNED_CONTENT_UNTIMESTAMPED",
]


@dataclass(frozen=True)
class PublisherEvidenceIntake:
    status: Status
    local_capture_replay_verified: bool
    provider_id: str
    capture_sha256: str
    publisher_signature_verified: bool
    publisher_available_at_proven: Literal[False] = False
    independently_timestamped_historical_release_verified: Literal[False] = False
    independent_historical_pit_verified: Literal[False] = False
    broker_executable: Literal[False] = False
    blocking_reasons: tuple[str, ...] = ()

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "local_capture_replay_verified": self.local_capture_replay_verified,
            "provider_id": self.provider_id,
            "capture_sha256": self.capture_sha256,
            "publisher_signature_verified": self.publisher_signature_verified,
            "publisher_available_at_proven": False,
            "independently_timestamped_historical_release_verified": False,
            "independent_historical_pit_verified": False,
            "broker_executable": False,
            "blocking_reasons": list(self.blocking_reasons),
        }


def audit_publisher_evidence(
    capture: CapturedPriceVintage,
    publisher_manifest_path: Path | None = None,
    publisher_signature_path: Path | None = None,
    *,
    decision_at: datetime | None = None,
) -> PublisherEvidenceIntake:
    """Replay actual source evidence and inspect an optional detached signed claim.

    A validated signature proves integrity of the claim relative to a pinned
    public key only. Claimed publication time is UNTRUSTED as historical
    timestamp data without a separately authenticated independent timestamp.
    """
    if decision_at is not None and (
        not isinstance(decision_at, datetime) or decision_at.tzinfo is None
        or decision_at.utcoffset() is None
    ):
        raise ValueError("decision_at timezone is required")
    if (publisher_manifest_path is None) != (publisher_signature_path is None):
        raise ResearchCatalogError("publisher evidence requires a manifest/signature pair")
    replay = verify_nasdaq_capture(
        capture.parquet_path, capture.raw_path, capture.manifest_path
    )
    with capture.manifest_path.open("r", encoding="utf-8") as handle:
        local = json.load(handle)
    source = urlsplit(local["source_url"])
    scope = parse_qs(source.query, strict_parsing=True)
    start = date.fromisoformat(scope["fromdate"][0])
    end = date.fromisoformat(scope["todate"][0])
    collected_at = datetime.fromisoformat(local["captured_at"]).astimezone(timezone.utc)
    common_blockers = (
        "independent_historical_publisher_timestamp_missing",
        "decision_time_market_data_availability_unverified",
    )

    def result(
        status: Status,
        *,
        signed: bool = False,
        reasons: tuple[str, ...] = (),
    ) -> PublisherEvidenceIntake:
        return PublisherEvidenceIntake(
            status=status,
            local_capture_replay_verified=True,
            provider_id="nasdaq-public",
            capture_sha256=replay.raw_sha256,
            publisher_signature_verified=signed,
            blocking_reasons=tuple(sorted(set(common_blockers + reasons))),
        )

    if publisher_manifest_path is None:
        return result(
            "PUBLISHER_PROOF_MISSING",
            reasons=("independent_publisher_proof_missing",),
        )
    assert publisher_signature_path is not None
    for path in (publisher_manifest_path, publisher_signature_path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_EVIDENCE:
            raise ResearchCatalogError("publisher evidence file missing/invalid")
    try:
        body = publisher_manifest_path.read_bytes()
        signature = publisher_signature_path.read_bytes()
        if len(signature) != 64:
            return result("INVALID_PUBLISHER_EVIDENCE", reasons=("invalid_signature",))
        proof = json.loads(body)
        if (
            not isinstance(proof, dict) or frozenset(proof) != _EVIDENCE_KEYS
            or not all(isinstance(value, str) for value in proof.values())
            or json.dumps(proof, sort_keys=True, separators=(",", ":")).encode() != body
            or proof["schema"] != "nasdaq-publisher-content-proof-v1"
            or proof["provider_id"] != "nasdaq-public"
            or _SHA256.fullmatch(proof["raw_sha256"]) is None
        ):
            return result("INVALID_PUBLISHER_EVIDENCE", reasons=("invalid_manifest",))
        claimed = datetime.fromisoformat(proof["asserted_published_at"])
        if claimed.tzinfo is None or claimed.utcoffset() is None:
            return result("INVALID_PUBLISHER_EVIDENCE", reasons=("invalid_timestamp",))
        claimed = claimed.astimezone(timezone.utc)
    except (ValueError, TypeError, KeyError, UnicodeError):
        return result("INVALID_PUBLISHER_EVIDENCE", reasons=("invalid_manifest",))
    trusted = TRUSTED_PUBLISHER_PUBLIC_KEYS.get(
        (proof["provider_id"], proof["publisher_key_id"])
    )
    if trusted is None:
        return result("UNTRUSTED_PUBLISHER_KEY", reasons=("trusted_publisher_key_missing",))
    try:
        Ed25519PublicKey.from_public_bytes(trusted).verify(signature, body)
    except (ValueError, InvalidSignature):
        return result("INVALID_PUBLISHER_EVIDENCE", reasons=("invalid_signature",))

    if proof["raw_sha256"] != replay.raw_sha256:
        return result("SOURCE_DIGEST_MISMATCH", reasons=("signed_content_digest_mismatch",))
    if (proof["coverage_start"], proof["coverage_end"]) != (
        start.isoformat(), end.isoformat()
    ):
        return result("SOURCE_SCOPE_MISMATCH", reasons=("signed_coverage_mismatch",))
    if decision_at is not None:
        cutoff = decision_at.astimezone(timezone.utc)
        # A local capture after the decision cannot be retrospectively
        # mistaken for evidence available at the old historical decision.
        if collected_at > cutoff:
            return result(
                "HISTORICAL_CAPTURE_TOO_LATE", signed=True,
                reasons=("local_snapshot_captured_after_decision",),
            )
        if claimed > cutoff:
            return result(
                "ASSERTED_PUBLICATION_AFTER_DECISION", signed=True,
                reasons=("asserted_publication_after_decision",),
            )
    return result(
        "SIGNED_CONTENT_UNTIMESTAMPED", signed=True,
        reasons=("publisher_claim_signature_only_not_historical_timestamp",),
    )
