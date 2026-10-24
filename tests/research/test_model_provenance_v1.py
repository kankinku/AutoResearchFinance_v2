"""P4-2 external capture guarantees are narrower than provider/model authenticity."""
import base64
import json
import sqlite3
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from foundation.hashes import canonical_bytes, content_hash
from research.llm.model_provenance_v1 import (
    SCOPE,
    ModelCaptureError,
    audit_capture_chain,
    last_hash,
    parse_public_key,
    store_capture,
    verify_capture,
)

SID = "d" * 32


def _keys():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private, public


def _receipt(private, *, gen=1, phase="plan", response=None, prior="0"*64):
    response = response if response is not None else {"model_plan": "demo"}
    body = {
        "schema": "p4-external-model-capture-v1",
        "session_id": SID,
        "generation": gen,
        "phase": phase,
        "provider": "openai",
        "model": "test-model",
        "collector_id": "signed-external-gateway",
        "invocation_id": f"external-{gen}-{phase}",
        "prompt_hash": "a"*64,
        "response_hash": content_hash(response),
        "checkpoint_context_hash": "b"*64,
        "checkpoint_token_hash": content_hash("token"),
        "prior_receipt_hash": prior,
        "decision_log_hash": "c"*64,
        "decision_summary": "Observed a loss case; change trend confirmation.",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "claim_scope": SCOPE,
    }
    return {**body, "signature_b64": base64.b64encode(
        private.sign(canonical_bytes(body))
    ).decode()}


def _check(receipt, key, *, gen=1, phase="plan", response=None, prior="0"*64):
    return verify_capture(receipt, key, session_id=SID, generation=gen, phase=phase,
                          response=response if response is not None else {"model_plan": "demo"},
                          context_hash="b"*64, checkpoint_token="token",
                          prior_receipt_hash=prior)


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE model_capture_receipts (session_id TEXT,generation INT,"
               "phase_order INT,record_json TEXT,receipt_hash TEXT,"
               "PRIMARY KEY(session_id,generation,phase_order))")
    return db


def test_signed_two_phase_chain_and_counted_evidence_is_immutable():
    secret, key = _keys()
    db = _db()
    plan = _receipt(secret)
    _check(plan, key)
    first = store_capture(db, plan, evidence_hash=None)
    assert last_hash(db, SID) == first
    assert audit_capture_chain(db, session_id=SID, public_key=key,
                               history=[], phase="AWAITING_DIAGNOSIS")["captured_steps"] == 1
    diagnosis = _receipt(secret, phase="diagnosis", response={"diagnosis": 1}, prior=first)
    _check(diagnosis, key, phase="diagnosis", response={"diagnosis": 1}, prior=first)
    digest = "f"*64
    store_capture(db, diagnosis, evidence_hash=digest)
    verified = audit_capture_chain(db, session_id=SID, public_key=key,
                                   history=[{"evidence_hash": digest}], phase="COMPLETED")
    assert verified["captured_steps"] == 2
    assert verified["provider_signed_receipt_verified"] is False
    assert verified["independent_model_invocation_verified"] is False
    assert verified["external_collector_signature_verified"] is True
    with pytest.raises(ModelCaptureError):
        audit_capture_chain(db, session_id=SID, public_key=key,
                            history=[{"evidence_hash": "b"*64}], phase="COMPLETED")
    with pytest.raises(sqlite3.IntegrityError):
        store_capture(db, diagnosis, evidence_hash=digest)
    assert len(db.execute("SELECT * FROM model_capture_receipts").fetchall()) == 2


def test_signatures_reject_tampering_wrong_key_payload_and_context():
    secret, public = _keys()
    _, wrong = _keys()
    receipt = _receipt(secret)
    for changed in (
        {**receipt, "decision_summary": "Made up conclusion"},
        {**receipt, "prompt_hash": "1"*64},
        {**receipt, "response_hash": "f"*64},
        {**receipt, "provider": "untrusted-name"},
        {**receipt, "signature_b64": "not base64"},
    ):
        with pytest.raises(ModelCaptureError):
            _check(changed, public)
    with pytest.raises(ModelCaptureError):
        _check(receipt, wrong)
    with pytest.raises(ModelCaptureError):
        _check(receipt, public, response={"model_plan": "not submitted"})
    with pytest.raises(ModelCaptureError):
        _check(receipt, public, prior="f"*64)
    with pytest.raises(ModelCaptureError):
        verify_capture(receipt, public, session_id=SID, generation=1, phase="plan",
                       response={"model_plan": "demo"}, context_hash="e"*64,
                       checkpoint_token="token", prior_receipt_hash="0"*64)
    with pytest.raises(ModelCaptureError):
        parse_public_key("f"*63)
    assert parse_public_key(public.hex()) == public


def test_mutated_envelope_with_recomputed_hash_still_fails_signature():
    secret, key = _keys()
    db = _db()
    signed = _receipt(secret)
    store_capture(db, signed, evidence_hash=None)
    row = db.execute("SELECT record_json FROM model_capture_receipts").fetchone()
    body = json.loads(row["record_json"])
    body["receipt"]["decision_summary"] = "falsified claim"
    db.execute("UPDATE model_capture_receipts SET record_json=?,receipt_hash=?",
               (canonical_bytes(body).decode(), content_hash(body)))
    with pytest.raises(ModelCaptureError, match="chain"):
        audit_capture_chain(db, session_id=SID, public_key=key,
                            history=[], phase="AWAITING_DIAGNOSIS")


def test_out_of_order_and_no_signed_data_are_not_treated_as_success():
    secret, key = _keys()
    db = _db()
    assert audit_capture_chain(db, session_id=SID, public_key=key,
                               history=[], phase="AWAITING_PLAN")["captured_steps"] == 0
    with pytest.raises(ModelCaptureError, match="incomplete"):
        audit_capture_chain(db, session_id=SID, public_key=key,
                            history=[{"evidence_hash": "f"*64}], phase="COMPLETED")
    signed = _receipt(secret, phase="diagnosis")
    store_capture(db, signed, evidence_hash="f"*64)
    with pytest.raises(ModelCaptureError):
        audit_capture_chain(db, session_id=SID, public_key=key,
                            history=[{"evidence_hash": "f"*64}], phase="COMPLETED")


def test_audit_rejects_malformed_base64_and_extra_fields_with_controlled_error():
    secret, key = _keys()
    db = _db()
    receipt = _receipt(secret)
    first = store_capture(db, receipt, evidence_hash=None)
    assert first == last_hash(db, SID)
    for damaged in (
        {**receipt, "signature_b64": "$$not-base64$$"},
        {**receipt, "injected_provider_signed": True},
    ):
        body = {"receipt": damaged, "counted_evidence_hash": None}
        db.execute(
            "UPDATE model_capture_receipts SET record_json=?,receipt_hash=?",
            (canonical_bytes(body).decode(), content_hash(body)),
        )
        with pytest.raises(ModelCaptureError, match="evidence chain invalid"):
            audit_capture_chain(
                db, session_id=SID, public_key=key,
                history=[], phase="AWAITING_DIAGNOSIS",
            )
