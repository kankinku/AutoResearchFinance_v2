"""Read-only P0 capability check; never asks a model to generate or changes OAuth.

The existing ChatGPT↔MCP client is the authorized decision-maker. This check
does not assert a model is available because an MCP tool or a collector exists.
An upstream model provider invocation must be independently evidenced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class CheckpointReader(Protocol):
    def get(self, args: dict[str, Any]) -> dict[str, Any]: ...


def audit_t4_model_host(
    reader: CheckpointReader,
    *,
    session_id: str,
    callback: object | None = None,
) -> dict[str, Any]:
    """Classify missing model host and real invocation proof without mutation.

    A bound callback means only that Python can call a function. This is NOT
    authentication or model provenance. The existing service's audit is the
    only source of provider-call verification, when present.
    """
    state = reader.get({"session_id": session_id})
    if state.get("session_id") != session_id:
        raise ValueError("checkpoint session identity mismatch")
    if state.get("orders_enabled") is not False:
        raise ValueError("protected research state: trading must remain disabled")
    if state.get("independent_oos_approved") is not False:
        raise ValueError("protected research state: sealed OOS not approved")
    completed = state.get("completed_generations")
    requested = state.get("requested_generations")
    if (
        type(completed) is not int
        or type(requested) is not int
        or requested < 1
        or completed < 0
        or completed > requested
    ):
        raise ValueError("invalid counted generation count")
    phase = state.get("checkpoint_phase")
    if phase not in {"AWAITING_PLAN", "AWAITING_DIAGNOSIS", "COMPLETED"}:
        raise ValueError("unsupported checkpoint phase for model execution")

    provider = state.get("model_capture_audit")
    capture = provider if isinstance(provider, Mapping) else {}
    upstream_verified = capture.get("independent_model_invocation_verified") is True
    collector_verified = capture.get("external_collector_signature_verified") is True
    callback_present = callable(getattr(callback, "propose", None))
    if not callback_present:
        status = "BLOCKED_NO_AUTHENTICATED_MODEL_HOST"
    elif not upstream_verified:
        status = "BLOCKED_PROVIDER_INVOCATION_UNVERIFIED"
    else:
        status = "PRIOR_PROVIDER_AUDIT_PRESENT_CURRENT_CALL_UNVERIFIED"

    return {
        "schema": "t4-model-host-readiness-v1",
        "mode": "READ_ONLY",
        "status": status,
        "checkpoint_phase": phase,
        "completed_generations": completed,
        "target_generations": requested,
        "remaining_generations": requested - completed,
        "callback_present": callback_present,
        "collector_signature_verified": collector_verified,
        "model_invocation_verified": upstream_verified,
        # A previous provider receipt never attests that the next callback is a model.
        "can_advance_genuine_generations": False,
        "previous_invocation_prerequisites_present": callback_present and upstream_verified,
        "oauth_changes_performed": False,
        "orders_enabled": False,
        "independent_oos_approved": False,
        "no_model_request_performed": True,
        "unattended_runner_started": False,
    }
