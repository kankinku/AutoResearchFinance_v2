"""V02: fail-closed publication-evidence inventory for retained Nasdaq QQQ.

Neither local retrieval timestamps nor vendor modification metadata establish
what historic traders could observe. No PIT promotion or broker integration.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_archive_inventory import _discover, audit_nasdaq_qqq_archive
from research.indicator_engine.publisher_evidence_intake import audit_publisher_evidence


def audit_publication_coverage(
    root: Path, start: date, end: date, *,
    decision_at: datetime | None = None,
) -> dict[str, Any]:
    """Audit all source captures with optional detached publisher claims."""
    if decision_at is not None and (
        not isinstance(decision_at, datetime)
        or decision_at.tzinfo is None
        or decision_at.utcoffset() is None
    ):
        raise ResearchCatalogError("historical decision time must be timezone aware")
    cutoff = decision_at.astimezone(timezone.utc) if decision_at else None
    inventory = audit_nasdaq_qqq_archive(root, start, end)
    records: list[dict[str, Any]] = []
    for capture, _ in _discover(root) if root.exists() else ():
        manifest = json.loads(capture.manifest_path.read_text(encoding="utf-8"))
        collected_at = datetime.fromisoformat(manifest["captured_at"]).astimezone(timezone.utc)
        prefix = capture.manifest_path.name.removesuffix(".manifest.json")
        proof = capture.manifest_path.parent / (prefix + ".publisher-claim.json")
        signature = capture.manifest_path.parent / (prefix + ".publisher-claim.sig")
        if proof.exists() != signature.exists():
            raise ResearchCatalogError("publisher evidence manifest/signature pair incomplete")
        checked = audit_publisher_evidence(
            capture,
            proof if proof.exists() else None,
            signature if signature.exists() else None,
            decision_at=cutoff,
        )
        records.append({
            "raw_sha256": checked.capture_sha256,
            "captured_at": collected_at.isoformat(),
            "local_capture_after_decision": (
                collected_at > cutoff if cutoff is not None else None
            ),
            "publisher_evidence_status": checked.status,
            "publisher_signature_verified": checked.publisher_signature_verified,
            "publisher_available_at_proven": False,
            "independent_timestamp_verified": False,
            "historical_pit_verified": False,
            "broker_executable": False,
            "blocking_reasons": list(checked.blocking_reasons),
        })
    records.sort(key=lambda record: (record["captured_at"], record["raw_sha256"]))
    if len(records) != inventory.verified_capture_count:
        raise ResearchCatalogError("archive inventory and evidence matrix mismatch")
    counts = dict(sorted(Counter(x["publisher_evidence_status"] for x in records).items()))
    late = sum(x["local_capture_after_decision"] is True for x in records)
    if not records:
        status = "NO_ARCHIVED_SOURCE"
    elif late:
        status = "HISTORICAL_CAPTURE_AFTER_DECISION_BLOCKED"
    elif any(x["publisher_evidence_status"] in {
        "UNTRUSTED_PUBLISHER_KEY", "INVALID_PUBLISHER_EVIDENCE",
        "SOURCE_DIGEST_MISMATCH", "SOURCE_SCOPE_MISMATCH",
    } for x in records):
        status = "UNTRUSTED_OR_INVALID_PUBLISHER_PROOF"
    else:
        status = "INDEPENDENT_HISTORICAL_PUBLICATION_PROOF_MISSING"
    report: dict[str, Any] = {
        "schema": "v02-nasdaq-publication-evidence-matrix-v1",
        "status": status,
        "scope": {"symbol": "QQQ", "from": start.isoformat(), "to": end.isoformat()},
        "decision_at": cutoff.isoformat() if cutoff else None,
        "inventory_hash": inventory.inventory_hash,
        "source_capture_count": len(records),
        "verified_local_source_count": inventory.verified_capture_count,
        "capture_after_decision_count": late,
        "publisher_proof_status_counts": counts,
        "historical_publication_attested_captures": 0,
        "captures": records,
        "required_external_evidence": [
            "provider-authorized historical publication/availability timestamps",
            "independent authentic vintage and publisher signing authority",
            "source and instrument identifiers bound to decision-time availability",
            "data retention/use permissions for QQQ historical source",
        ],
        "dataset_condition_is_per_day_not_per_instrument": True,
        "local_retrieval_is_not_historical_availability": True,
        "point_in_time_verified": False,
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    report["report_hash"] = content_hash(report)
    return report
