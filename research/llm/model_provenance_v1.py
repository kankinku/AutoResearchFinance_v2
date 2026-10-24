"""P4-2: signed external capture assertions for opted-in GPT research checkpoints.

A signature attests what a *configured external capture service* asserted;
it DOES NOT authenticate a model provider's infrastructure or prove a model
invocation happened. Do not call these provider receipts without a provider-
signed, independently verifiable upstream receipt. No secrets or private keys
are stored here. Immutable counted strategy/diagnosis evidence is unchanged.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from foundation.hashes import canonical_bytes, content_hash


class ModelCaptureError(ValueError):
    """Invalid, missing, unauthenticated or inconsistent capture assertion."""


SHA = re.compile(r"[a-f0-9]{64}\Z")
SESSION = re.compile(r"[a-f0-9]{32}\Z")
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
PHASES = {"plan": 0, "diagnosis": 1}
CAPTURE_FIELDS = frozenset({
    "schema", "session_id", "generation", "phase", "provider", "model",
    "invocation_id", "collector_id", "prompt_hash", "response_hash",
    "checkpoint_context_hash", "checkpoint_token_hash", "prior_receipt_hash",
    "decision_log_hash", "decision_summary", "captured_at", "claim_scope",
    "signature_b64",
})
SCOPE = "EXTERNAL_COLLECTOR_SIGNATURE_NOT_PROVIDER_ATTESTATION"


def parse_public_key(public_key_hex: str) -> bytes:
    if not isinstance(public_key_hex, str) or re.fullmatch(r"[0-9a-f]{64}", public_key_hex) is None:
        raise ModelCaptureError("P4-2 trusted Ed25519 capture public key must be 32-byte hex")
    return bytes.fromhex(public_key_hex)


def verify_capture(
    receipt: Mapping[str, Any], public_key: bytes, *, session_id: str,
    generation: int, phase: str, response: Any, context_hash: str,
    checkpoint_token: str, prior_receipt_hash: str,
) -> dict[str, Any]:
    """Verify caller-supplied SIGNED capture against the actual accepted payload."""
    if not isinstance(receipt, Mapping) or set(receipt) != CAPTURE_FIELDS:
        raise ModelCaptureError("P4-2 exact signed capture fields required")
    if (receipt["schema"] != "p4-external-model-capture-v1"
        or receipt["claim_scope"] != SCOPE
        or receipt["session_id"] != session_id
        or receipt["generation"] != generation
        or receipt["phase"] != phase
        or phase not in PHASES
        or SESSION.fullmatch(session_id) is None
        or receipt["response_hash"] != content_hash(response)
        or receipt["checkpoint_context_hash"] != context_hash
        or receipt["checkpoint_token_hash"] != content_hash(checkpoint_token)
        or receipt["prior_receipt_hash"] != prior_receipt_hash):
        raise ModelCaptureError("P4-2 capture context, generation or response mismatch")
    if any(
        not isinstance(receipt[field], str) or IDENTITY.fullmatch(receipt[field]) is None
        for field in ("provider", "model", "collector_id", "invocation_id")
    ):
        raise ModelCaptureError("P4-2 invalid attributed model/capture identity")
    if any(
        not isinstance(receipt[field], str) or SHA.fullmatch(receipt[field]) is None
        for field in ("prompt_hash", "response_hash", "checkpoint_context_hash",
                      "checkpoint_token_hash", "prior_receipt_hash", "decision_log_hash")
    ):
        raise ModelCaptureError("P4-2 invalid source content digest")
    if not isinstance(receipt["decision_summary"], str) or not (
        1 <= len(receipt["decision_summary"]) <= 500
    ):
        raise ModelCaptureError("P4-2 concise decision log required")
    try:
        at = datetime.fromisoformat(receipt["captured_at"])
        if at.utcoffset() is None:
            raise ValueError("naive timestamp")
        signature = base64.b64decode(receipt["signature_b64"], validate=True)
        if len(signature) != 64:
            raise ValueError("invalid signature length")
        body = {k: v for k, v in receipt.items() if k != "signature_b64"}
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, canonical_bytes(body))
    except (ValueError, TypeError, binascii.Error, InvalidSignature) as exc:
        raise ModelCaptureError("P4-2 collector signature or timestamp invalid") from exc
    return dict(receipt)


def last_hash(db: sqlite3.Connection, session_id: str) -> str:
    row = db.execute(
        "SELECT receipt_hash FROM model_capture_receipts WHERE session_id=? "
        "ORDER BY generation DESC, phase_order DESC LIMIT 1", (session_id,),
    ).fetchone()
    return str(row[0]) if row is not None else "0" * 64


def store_capture(
    db: sqlite3.Connection, receipt: Mapping[str, Any], *,
    evidence_hash: str | None,
) -> str:
    """Call only after a successful canonical checkpoint; same SQL transaction."""
    if evidence_hash is not None and (not isinstance(evidence_hash, str)
                                     or SHA.fullmatch(evidence_hash) is None):
        raise ModelCaptureError("P4-2 missing canonical counted evidence hash")
    record = {"receipt": dict(receipt), "counted_evidence_hash": evidence_hash}
    receipt_hash = content_hash(record)
    db.execute(
        "INSERT INTO model_capture_receipts "
        "(session_id,generation,phase_order,record_json,receipt_hash) VALUES(?,?,?,?,?)",
        (receipt["session_id"], receipt["generation"], PHASES[receipt["phase"]],
         canonical_bytes(record).decode("utf-8"), receipt_hash),
    )
    return receipt_hash


def audit_capture_chain(
    db: sqlite3.Connection, *, session_id: str, public_key: bytes,
    history: Sequence[Mapping[str, Any]], phase: str,
) -> dict[str, Any]:
    rows = db.execute(
        "SELECT generation,phase_order,record_json,receipt_hash "
        "FROM model_capture_receipts WHERE session_id=? "
        "ORDER BY generation,phase_order", (session_id,),
    ).fetchall()
    previous = "0" * 64
    count = 0
    invocation_ids: set[tuple[str, str]] = set()
    for row in rows:
        try:
            record = json.loads(row["record_json"])
            receipt = record["receipt"]
            gen, stage = row["generation"], row["phase_order"]
            if (set(record) != {"receipt", "counted_evidence_hash"}
                or not isinstance(receipt, dict)
                or set(receipt) != CAPTURE_FIELDS
                or receipt["schema"] != "p4-external-model-capture-v1"
                or receipt["claim_scope"] != SCOPE
                or stage not in (0, 1)
                or receipt["session_id"] != session_id
                or receipt["generation"] != gen
                or receipt["phase"] != ("plan" if stage == 0 else "diagnosis")
                or receipt["prior_receipt_hash"] != previous
                or content_hash(record) != row["receipt_hash"]
                or (gen,stage) != ((count // 2) + 1, count % 2)):
                raise ModelCaptureError("P4-2 chained checkpoint order/hash changed")
            if stage == 0:
                if record["counted_evidence_hash"] is not None:
                    raise ModelCaptureError("P4-2 plan cannot claim committed evidence")
            elif gen > len(history) or (
                record["counted_evidence_hash"] != history[gen - 1]["evidence_hash"]
            ):
                raise ModelCaptureError("P4-2 diagnosis not tied to counted evidence")
            # Signature cannot be forged by changing any covered capture field.
            body = {k: v for k, v in receipt.items() if k != "signature_b64"}
            signature = base64.b64decode(receipt["signature_b64"], validate=True)
            if len(signature) != 64:
                raise ModelCaptureError("P4-2 invalid signature size")
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature, canonical_bytes(body),
            )
            invocation = (receipt["collector_id"], receipt["invocation_id"])
            if invocation in invocation_ids:
                raise ModelCaptureError("P4-2 reused capture invocation identity")
            invocation_ids.add(invocation)
            previous = row["receipt_hash"]
            count += 1
        except (KeyError, ValueError, TypeError, binascii.Error, InvalidSignature) as exc:
            raise ModelCaptureError("P4-2 immutable collector evidence chain invalid") from exc
    if count // 2 != len(history) or (
        phase == "AWAITING_DIAGNOSIS" and count != len(history) * 2 + 1
    ) or (
        phase in {"AWAITING_PLAN", "COMPLETED"} and count != len(history) * 2
    ):
        raise ModelCaptureError("P4-2 incomplete collector chain for current checkpoint")
    return {
        "schema": "p4-model-capture-audit-v1",
        "captured_steps": count,
        "counted_generations": len(history),
        "chain_head": previous,
        "scope": SCOPE,
        "provider_signed_receipt_verified": False,
        "external_collector_signature_verified": True,
        "independent_model_invocation_verified": False,
        "orders_enabled": False,
        "independent_oos_approved": False,
    }
