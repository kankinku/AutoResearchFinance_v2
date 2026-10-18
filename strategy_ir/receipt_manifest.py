"""Pinned read-only feature evidence snapshot, never derived from a candidate plan."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from strategy_ir.feature_receipt import FeatureAuditReceipt


class PinnedReceiptManifest:
    """Load a separately approved snapshot by its SHA-256 digest.

    The expected digest must come from trusted application configuration, not a
    candidate/LLM request. This verifies bytes, not audit quality or PIT safety.
    """

    def __init__(self, path: Path, *, expected_sha256: str) -> None:
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("feature manifest digest mismatch")
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError("unsupported receipt manifest")
        entries = document.get("receipts")
        if not isinstance(entries, list):
            raise ValueError("receipt manifest entries required")
        records: dict[str, FeatureAuditReceipt] = {}
        for item in entries:
            if not isinstance(item, dict) or set(item) != {
                "feature_id",
                "dataset_hash",
                "values_hash",
                "verification_id",
                "verification_status",
            }:
                raise ValueError("invalid receipt entry")
            receipt = FeatureAuditReceipt(**item)
            if not receipt.feature_id.strip() or receipt.feature_id in records:
                raise ValueError("missing or duplicate feature ID")
            if receipt.verification_status != "AUDITED":
                raise ValueError("unapproved receipt in manifest")
            records[receipt.feature_id] = receipt
        self._records = records

    def lookup(self, feature_id: str) -> FeatureAuditReceipt | None:
        return self._records.get(feature_id)
