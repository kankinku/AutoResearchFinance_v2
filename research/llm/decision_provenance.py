"""P0-3: grounded client decision *claims*, NEVER proof a GPT reasoned.

MCP authentication identifies a connection, not the source model or the
actual reasoning process. All origin names are user-controlled declarations.
Only links to immutable measured S7 outcomes and observed diagnostic trade IDs
are verified here; this is not independent research-quality certification.
"""

from __future__ import annotations

from typing import Any

from core.integrity.hashes import content_hash


class DecisionProvenanceError(ValueError):
    """Malformed or ungrounded claim; do not advance the checkpoint."""


_ALLOWED_ORIGINS = frozenset({"CHATGPT_CLIENT", "SCRIPTED", "HUMAN", "UNSPECIFIED"})


def validate_decision_evidence(
    candidate: Any,
    *,
    phase: str,
    generation: int,
    measured_s7: dict[int, dict[str, Any]],
    audit_observations: set[str] | None = None,
) -> dict[str, Any]:
    """Check citations against authoritative S7 hashes, not model-supplied scores."""
    if (
        phase not in ("PLAN", "DIAGNOSIS")
        or type(generation) is not int
        or not 1 <= generation <= 100
    ):
        raise DecisionProvenanceError("invalid evidence checkpoint")
    if not isinstance(candidate, dict) or set(candidate) != {
        "declared_origin",
        "decision_summary",
        "rejected_alternative",
        "referenced_s7",
        "current_observation_ids",
    }:
        raise DecisionProvenanceError("decision_evidence requires exact bounded fields")
    origin = candidate["declared_origin"]
    if not isinstance(origin, str) or origin not in _ALLOWED_ORIGINS:
        raise DecisionProvenanceError("unsupported unverified origin declaration")
    for key, low, high in (("decision_summary", 32, 900), ("rejected_alternative", 24, 650)):
        text = candidate[key]
        if not isinstance(text, str) or not low <= len(text.strip()) <= high:
            raise DecisionProvenanceError(f"{key} must contain concise substantive rationale")
    references = candidate["referenced_s7"]
    if not isinstance(references, list) or not 0 <= len(references) <= 6:
        raise DecisionProvenanceError("unsupported S7 reference count")
    if generation > 1 and not references:
        raise DecisionProvenanceError("research decision must cite earlier measured S7")
    verified: list[dict[str, Any]] = []
    used: set[tuple[int, str]] = set()
    for ref in references:
        if not isinstance(ref, dict) or set(ref) != {
            "generation",
            "hypothesis_id",
            "s7_record_hash",
            "observed_status",
        }:
            raise DecisionProvenanceError("invalid S7 reference shape")
        g, hid = ref["generation"], ref["hypothesis_id"]
        if type(g) is not int or not 1 <= g < generation or not isinstance(hid, str):
            raise DecisionProvenanceError("only earlier S7 generations may be referenced")
        if (g, hid) in used:
            raise DecisionProvenanceError("duplicate S7 research citation")
        used.add((g, hid))
        stored = measured_s7.get(g)
        if stored is None or stored.get("record_hash") != ref["s7_record_hash"]:
            raise DecisionProvenanceError("S7 reference report hash does not match stored evidence")
        report = stored.get("report")
        observed = report.get("experiments", []) if isinstance(report, dict) else []
        experiment = next((x for x in observed if x.get("hypothesis_id") == hid), None)
        if experiment is None or experiment.get("status") != ref["observed_status"]:
            raise DecisionProvenanceError("cited S7 result does not match observed outcome")
        verified.append({**ref})
    ids = candidate["current_observation_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > 8
        or any(not isinstance(x, str) or not 2 <= len(x) <= 120 for x in ids)
        or len(ids) != len(set(ids))
    ):
        raise DecisionProvenanceError("invalid current diagnostic observation references")
    if phase == "PLAN" and ids:
        raise DecisionProvenanceError("plan cannot cite yet-unobserved current trades")
    if phase == "DIAGNOSIS" and (
        not ids or audit_observations is None or any(i not in audit_observations for i in ids)
    ):
        raise DecisionProvenanceError("diagnosis requires exact audited current trade IDs")
    return {
        "schema": "research-decision-evidence-v1",
        "phase": phase,
        "generation": generation,
        "declared_origin": origin,
        "origin_authenticity": "UNVERIFIED_CLIENT_CLAIM",
        "independent_model_reasoning_verified": False,
        "causal_learning_verified": False,
        "decision_summary": candidate["decision_summary"].strip(),
        "rejected_alternative": candidate["rejected_alternative"].strip(),
        "referenced_s7": verified,
        "current_observation_ids": list(ids),
    }


def bound_decision_receipt(
    *,
    session_id: str,
    submitted_hash: str,
    decision: dict[str, Any],
    ancestor_evidence_hash: str | None,
) -> dict[str, Any]:
    """Immutable-style supplementary digest; never alter canonical generation evidence."""
    if type(submitted_hash) is not str or len(submitted_hash) != 64:
        raise DecisionProvenanceError("invalid submitted payload digest")
    body = {
        "schema": "research-decision-receipt-v1",
        "session_id": session_id,
        "generation": decision["generation"],
        "phase": decision["phase"],
        "submitted_hash": submitted_hash,
        "ancestor_evidence_hash": ancestor_evidence_hash,
        "evidence": decision,
    }
    return {**body, "receipt_hash": content_hash(body)}


def verify_decision_receipt(receipt: dict[str, Any]) -> None:
    base = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if content_hash(base) != receipt.get("receipt_hash"):
        raise DecisionProvenanceError("research decision sidecar receipt corruption")
