"""T4-P0 native ChatGPT/MCP host readiness is read-only and never calls a model."""

from __future__ import annotations

from copy import deepcopy

import pytest

from application.t4_model_host_preflight import audit_t4_model_host


class FakeService:
    def __init__(self):
        self.lookups = 0
        self.state = {
            "session_id": "a" * 32,
            "completed_generations": 20,
            "requested_generations": 100,
            "checkpoint_phase": "AWAITING_PLAN",
            "checkpoint_token": "super-secret-checkpoint",
            "model_context": {"untrusted_prompt": "DO NOT EXPOSE RAW CONTEXT"},
            "orders_enabled": False,
            "independent_oos_approved": False,
            "history": [{"evidence_hash": "d" * 64}],
        }

    def get(self, params):
        assert params == {"session_id": "a" * 32}
        self.lookups += 1
        return deepcopy(self.state)


class NoCallModel:
    def __init__(self):
        self.called = 0

    def propose(self, _context):
        self.called += 1
        raise RuntimeError("P0 preflight must not call the provider")


def test_existing_p5_without_host_remains_blocked_and_preserves_state():
    svc = FakeService()
    before = deepcopy(svc.state)
    report = audit_t4_model_host(svc, session_id="a" * 32, callback=None)
    assert report["status"] == "BLOCKED_NO_AUTHENTICATED_MODEL_HOST"
    assert report["completed_generations"] == 20
    assert report["target_generations"] == 100
    assert report["mode"] == "READ_ONLY"
    assert report["model_invocation_verified"] is False
    assert report["can_advance_genuine_generations"] is False
    assert report["oauth_changes_performed"] is False
    assert "super-secret-checkpoint" not in str(report)
    assert "DO NOT EXPOSE RAW CONTEXT" not in str(report)
    assert svc.state == before
    assert svc.lookups == 1


def test_callback_is_not_evidence_of_actual_model_invocation():
    svc, model = FakeService(), NoCallModel()
    report = audit_t4_model_host(svc, session_id="a" * 32, callback=model)
    assert report["status"] == "BLOCKED_PROVIDER_INVOCATION_UNVERIFIED"
    assert report["callback_present"] is True
    assert not report["can_advance_genuine_generations"]
    assert model.called == 0


def test_p4_signed_collector_does_not_prove_provider_call():
    svc, model = FakeService(), NoCallModel()
    svc.state["model_capture_audit"] = {
        "external_collector_signature_verified": True,
        "provider_signed_receipt_verified": False,
        "independent_model_invocation_verified": False,
    }
    result = audit_t4_model_host(svc, session_id="a" * 32, callback=model)
    assert result["collector_signature_verified"] is True
    assert result["model_invocation_verified"] is False
    assert result["status"] == "BLOCKED_PROVIDER_INVOCATION_UNVERIFIED"


def test_verified_capture_and_actual_host_binding_are_separate_conditions():
    svc, model = FakeService(), NoCallModel()
    svc.state["model_capture_audit"] = {
        "independent_model_invocation_verified": True,
        "provider_signed_receipt_verified": True,
    }
    missing_callback = audit_t4_model_host(svc, session_id="a" * 32)
    assert missing_callback["status"] == "BLOCKED_NO_AUTHENTICATED_MODEL_HOST"
    report = audit_t4_model_host(svc, session_id="a" * 32, callback=model)
    assert report["status"] == "PRIOR_PROVIDER_AUDIT_PRESENT_CURRENT_CALL_UNVERIFIED"
    assert report["model_invocation_verified"]
    assert not report["can_advance_genuine_generations"]
    assert model.called == 0


@pytest.mark.parametrize("key", ["orders_enabled", "independent_oos_approved"])
def test_forbidden_trading_or_oos_states_fail_closed(key):
    svc = FakeService()
    svc.state[key] = True
    with pytest.raises(ValueError, match="protected"):
        audit_t4_model_host(svc, session_id="a" * 32)


def test_untrusted_session_identity_and_generation_gate():
    svc = FakeService()
    svc.state["completed_generations"] = 102
    with pytest.raises(ValueError, match="count"):
        audit_t4_model_host(svc, session_id="a" * 32)
    svc.state["completed_generations"] = 20
    svc.state["session_id"] = "b" * 32
    with pytest.raises(ValueError, match="identity"):
        audit_t4_model_host(svc, session_id="a" * 32)
