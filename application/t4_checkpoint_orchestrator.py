"""T4 checkpoint-bound continuation for an externally supplied ChatGPT/MCP model.

This module does NOT call an LLM or assert source provenance.  A trusted host must
supply an actual model callback.  Test callbacks are NEVER real generations.
Canonical audit/S7/lineage ownership remains with AcademicMCPCheckpointService.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any, Literal, Protocol

from research.llm.s2_execution_preflight import UnchangedCanonicalExecution
from research.llm.s7_quality_gate_p4_3 import P4S7Rejected


class ModelUnavailable(RuntimeError):
    """No model or unable to obtain a real externally authored decision."""


class CheckpointUncertain(RuntimeError):
    """Do not advance after a backend exception if state cannot be re-read."""


class CheckpointService(Protocol):
    def get(self, args: dict[str, Any]) -> dict[str, Any]: ...
    def submit_plan(self, args: dict[str, Any]) -> dict[str, Any]: ...
    def submit_diagnosis(self, args: dict[str, Any]) -> dict[str, Any]: ...


class ModelCallback(Protocol):
    def propose(self, context: dict[str, Any]) -> Mapping[str, Any]: ...


_ALLOWED_REJECTION_MARKERS = (
    "UNCHANGED_CANONICAL_FILLS",
    "P4_S7_QUALITY_REJECTED",
    "P4_S7",
    "NO_OBSERVED_EFFECT",
    "unsupported S7 metric",
    "known static no-op experiment",
    "INTENT_",
    "not executable",
)


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, (UnchangedCanonicalExecution, P4S7Rejected)):
        return True
    return isinstance(exc, ValueError) and any(
        marker in str(exc) for marker in _ALLOWED_REJECTION_MARKERS
    )


def _authoritative(service: CheckpointService, session_id: str) -> dict[str, Any]:
    checkpoint = service.get({"session_id": session_id})
    if checkpoint.get("orders_enabled") is not False:
        raise ValueError("research order execution must stay disabled")
    if checkpoint.get("independent_oos_approved") is not False:
        raise ValueError("independent OOS must remain sealed")
    if checkpoint.get("session_id") != session_id:
        raise ValueError("checkpoint session mismatch")
    done = checkpoint.get("completed_generations")
    requested = checkpoint.get("requested_generations")
    if type(done) is not int or type(requested) is not int or not 0 <= done <= requested:
        raise ValueError("untrusted completed/requested generation counts")
    return checkpoint


def run_checkpoint_loop(
    service: CheckpointService,
    *,
    session_id: str,
    model: ModelCallback | None,
    target_generations: int | None = None,
    mode: Literal["TEST_ONLY", "EXTERNAL_MCP_UNVERIFIED"] = "EXTERNAL_MCP_UNVERIFIED",
    max_model_calls: int | None = None,
    max_retries_per_checkpoint: int = 2,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Run until target or a real stop condition, without arbitrary ten-gen blocks.

    Existing checkpoint service is the *sole* authority for generation counts.
    A test-double's 100/100 result is labeled TEST_ONLY and cannot attest to an
    actual model call, independent OOS, or economic profitability.

    Model invocation cannot be manufactured by this orchestrator; it must be
    supplied by an authenticated external host. This entry point neither
    installs a provider nor changes ChatGPT/MCP/OAuth default connections.
    """
    if model is None or not callable(getattr(model, "propose", None)):
        raise ModelUnavailable("authenticated external ChatGPT/MCP model callback is unavailable")
    if mode not in ("TEST_ONLY", "EXTERNAL_MCP_UNVERIFIED"):
        raise ValueError("unrecognized model invocation mode")
    if type(max_retries_per_checkpoint) is not int or not 0 <= max_retries_per_checkpoint <= 8:
        raise ValueError("retry budget out of range")
    if max_model_calls is not None and (type(max_model_calls) is not int or max_model_calls < 1):
        raise ValueError("model call budget must be positive")
    state = _authoritative(service, session_id)
    desired = state["requested_generations"] if target_generations is None else target_generations
    if (
        type(desired) is not int
        or not state["completed_generations"] <= desired <= state["requested_generations"]
    ):
        raise ValueError("target outside pinned study boundaries")
    initial = state["completed_generations"]
    calls = 0
    lost_replies = 0
    rejections = 0
    status = "TARGET_REACHED" if initial == desired else "WAITING"

    while state["completed_generations"] < desired:
        if should_stop is not None and should_stop():
            status = "STOP_REQUESTED"
            break
        if max_model_calls is not None and calls >= max_model_calls:
            status = "MODEL_CALL_BUDGET_REACHED"
            break
        phase = state.get("checkpoint_phase")
        if phase not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
            raise ValueError(f"unexpected research checkpoint phase: {phase}")
        ctx = state.get("model_context")
        token = state.get("checkpoint_token")
        if not isinstance(ctx, dict) or not isinstance(token, str) or not token:
            raise ValueError("missing verified model context or checkpoint token")
        feedback: str | None = None
        attempt = 0
        while True:
            if should_stop is not None and should_stop():
                status = "STOP_REQUESTED"
                break
            if max_model_calls is not None and calls >= max_model_calls:
                status = "MODEL_CALL_BUDGET_REACHED"
                break
            context = deepcopy(ctx)
            if feedback is not None:
                context["research_loop_feedback"] = {
                    "rejected_checkpoint_phase": phase,
                    "failure": feedback,
                    "action": "revise_model_output_without_spending_generation",
                }
            calls += 1
            try:
                authored = model.propose(context)
            except Exception as exc:
                raise ModelUnavailable(
                    "external model callback failed; checkpoint unchanged"
                ) from exc
            if not isinstance(authored, Mapping):
                raise ValueError("external model did not return a structured object")
            args: dict[str, Any] = {
                "session_id": session_id,
                "checkpoint_token": token,
                "plan" if phase == "AWAITING_PLAN" else "diagnosis": dict(authored),
            }
            if phase == "AWAITING_PLAN":
                # Demand *real changed fills* on verified inherited parent updates.
                if ctx.get("counted_parent_inheritance_ready"):
                    args["require_execution_change"] = True
                submit = service.submit_plan
            else:
                submit = service.submit_diagnosis
            try:
                submit(args)
            except Exception as exc:
                try:
                    after = _authoritative(service, session_id)
                except Exception as read_exc:
                    raise CheckpointUncertain(
                        "backend receipt unavailable; inspect canonical checkpoint before resuming"
                    ) from read_exc
                # The commit may have succeeded and only the transport reply got lost.
                if after["completed_generations"] > state["completed_generations"] or (
                    after.get("checkpoint_phase") != phase
                    and after.get("checkpoint_token") != token
                ):
                    # The original checkpoint service authenticates duplicate
                    # *payload and token* via the recent-submission receipt.
                    # Merely observing a changed phase could be another caller.
                    try:
                        submit(args)
                    except Exception as replay_exc:
                        raise CheckpointUncertain(
                            "lost reply not tied to this model response"
                        ) from replay_exc
                    state = _authoritative(service, session_id)
                    lost_replies += 1
                    break
                if after.get("checkpoint_token") != token or after.get("checkpoint_phase") != phase:
                    raise CheckpointUncertain(
                        "checkpoint changed unexpectedly; stop rather than duplicate"
                    ) from exc
                if not _retryable(exc):
                    raise
                attempt += 1
                rejections += 1
                if attempt > max_retries_per_checkpoint:
                    status = "RETRY_EXHAUSTED"
                    break
                feedback = f"{type(exc).__name__}: {str(exc)[:320]}"
                # Include immutable service rejection feedback in fresh model context.
                ctx = after["model_context"]
            else:
                after = _authoritative(service, session_id)
                if after["completed_generations"] == state["completed_generations"] and (
                    after["checkpoint_phase"] == phase or after["checkpoint_token"] == token
                ):
                    raise CheckpointUncertain(
                        "successful submission did not advance the checkpoint"
                    )
                state = after
                break
        if status in ("STOP_REQUESTED", "MODEL_CALL_BUDGET_REACHED", "RETRY_EXHAUSTED"):
            break
    else:
        status = "TARGET_REACHED"

    final = _authoritative(service, session_id)
    if final["completed_generations"] < initial or final["completed_generations"] > desired:
        raise CheckpointUncertain("unexpected counted generation drift")
    capture = final.get("model_capture_audit", {})
    capture = capture if isinstance(capture, Mapping) else {}
    return {
        "schema": "t4-checkpoint-orchestrator-summary-v1",
        "status": status,
        "mode": mode,
        "initial_generations": initial,
        "completed_generations": final["completed_generations"],
        "new_generations": final["completed_generations"] - initial,
        "requested_generations": final["requested_generations"],
        "target_generations": desired,
        "checkpoint_phase": final["checkpoint_phase"],
        "model_calls": calls,
        "recoverable_rejections": rejections,
        "recovered_reply_losses": lost_replies,
        "real_provider_verified": bool(capture.get("independent_model_invocation_verified"))
        if mode != "TEST_ONLY"
        else False,
        "independent_oos_approved": False,
        "orders_enabled": False,
    }
