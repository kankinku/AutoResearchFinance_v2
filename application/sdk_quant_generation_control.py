"""Fail-closed SDK control plane for *existing* Quant MCP academic generations.

The SDK has no trading logic, LLM, write-capable MCP client or production host
adapter. Only an explicitly marked isolated fixture host can be dispatched in
this module. A real ChatGPT host-dispatch API must be verified and integrated
separately before production iteration can be enabled.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from application.sdk_quant_run_lease import scoped_sdk_run_lease


class UnsafeCheckpoint(ValueError):
    """Quant state changed, did not prove one generation, or is unsafe."""


class BlockedHostDispatch(RuntimeError):
    """No trustworthy host dispatch; never generate a strategy in the SDK."""


class CheckpointReader(Protocol):
    def get(self, args: dict[str, Any]) -> dict[str, Any]: ...


class TestFixtureHost(Protocol):
    fixture_only: bool

    def dispatch(self, request: dict[str, Any]) -> None: ...


_ALLOWED = {"AWAITING_PLAN", "AWAITING_DIAGNOSIS", "COMPLETED"}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SID = re.compile(r"[0-9a-f]{32}\Z")


def analyze_checkpoint(state: Mapping[str, Any], *, expected_session: str) -> dict[str, Any]:
    """Validate Quant's advertised checkpoint; do not inspect/modify sealed data."""
    if not _SID.fullmatch(expected_session) or state.get("session_id") != expected_session:
        raise UnsafeCheckpoint("research session mismatch")
    if (
        state.get("orders_enabled") is not False
        or state.get("independent_oos_approved") is not False
    ):
        raise UnsafeCheckpoint("orders/OOS safety contract is not sealed")
    dataset = state.get("dataset_hash")
    if not isinstance(dataset, str) or not _SHA.fullmatch(dataset):
        raise UnsafeCheckpoint("untrusted development dataset identity")
    done, requested = state.get("completed_generations"), state.get("requested_generations")
    if type(done) is not int or type(requested) is not int or not 0 <= done <= requested <= 1000:
        raise UnsafeCheckpoint("invalid generation limits")
    phase = state.get("checkpoint_phase")
    if phase not in _ALLOWED:
        raise UnsafeCheckpoint("unexpected checkpoint phase")
    if (done == requested) != (phase == "COMPLETED"):
        raise UnsafeCheckpoint("checkpoint completion mismatch")
    if state.get("status") != ("COMPLETED" if done == requested else "AWAITING_PROVIDER"):
        raise UnsafeCheckpoint("checkpoint session status mismatch")
    if done < requested:
        token = state.get("checkpoint_token")
        context = state.get("model_context")
        if (
            not isinstance(token, str)
            or not token
            or not isinstance(context, Mapping)
            or not isinstance(context.get("context_hash"), str)
            or not context["context_hash"]
        ):
            raise UnsafeCheckpoint("missing phase token or model context")
    history = state.get("history")
    if not isinstance(history, list) or len(history) != done:
        raise UnsafeCheckpoint("history count mismatch")
    for gen, row in enumerate(history, start=1):
        if (
            not isinstance(row, Mapping)
            or row.get("generation") != gen
            or not isinstance(row.get("evidence_hash"), str)
            or not _SHA.fullmatch(row["evidence_hash"])
        ):
            raise UnsafeCheckpoint("generation evidence sequence invalid")
    head = history[-1]["evidence_hash"] if history else None
    return {
        "session_id": expected_session,
        "completed": done,
        "requested": requested,
        "phase": phase,
        "token": state.get("checkpoint_token"),
        "dataset_hash": dataset,
        "head_hash": head,
        "context_hash": (state["model_context"]["context_hash"] if done < requested else None),
    }


def _run_sdk_generation_loop_unlocked(
    service: CheckpointReader,
    *,
    session_id: str,
    target: int,
    host: TestFixtureHost | None = None,
    fixture_mode: bool = False,
    max_dispatches: int = 10,
) -> dict[str, Any]:
    """Read-only preflight by default; fixture dispatch is never official GPT research.

    The contract is intentionally not an unauthenticated MCP write client.
    It proves budget/count/state-machine behavior without bypassing the stricter
    T4 model provenance gate or inventing SDK-triggered host turns.
    """
    initial = analyze_checkpoint(
        service.get({"session_id": session_id}), expected_session=session_id
    )
    if type(target) is not int or not initial["completed"] <= target <= initial["requested"]:
        raise ValueError("target must be within existing Quant study boundaries")
    if type(max_dispatches) is not int or not 1 <= max_dispatches <= 100:
        raise ValueError("SDK dispatch budget must be 1..100")
    if initial["completed"] == target:
        status = "TARGET_REACHED"
    elif host is None:
        status = "BLOCKED_MODEL_HOST_DISPATCH"
    elif not fixture_mode or getattr(host, "fixture_only", False) is not True:
        raise BlockedHostDispatch("external host is not authenticated; cannot dispatch GPT turns")
    else:
        status = "DISPATCH_BUDGET_EXHAUSTED"
    prior = initial
    turns = 0
    while host is not None and fixture_mode and prior["completed"] < target:
        if getattr(host, "fixture_only", False) is not True:
            raise BlockedHostDispatch("untrusted model host")
        if turns >= max_dispatches:
            break
        request = {
            "session_id": session_id,
            "generation": prior["completed"] + 1,
            "checkpoint_phase": prior["phase"],
            "checkpoint_token": prior["token"],
            "context_hash": prior["context_hash"],
            "dataset_hash": prior["dataset_hash"],
        }
        turns += 1
        try:
            host.dispatch(request)
        except Exception as exc:
            # Some backend writes may have succeeded; do not replay a turn.
            raise BlockedHostDispatch(
                "model response uncertain; reconcile before any retry"
            ) from exc
        raw_after = service.get({"session_id": session_id})
        after = analyze_checkpoint(raw_after, expected_session=session_id)
        if (
            prior["completed"] > 0
            and raw_after["history"][prior["completed"] - 1]["evidence_hash"] != prior["head_hash"]
        ):
            raise UnsafeCheckpoint("existing evidence head changed during dispatch")
        if after["dataset_hash"] != initial["dataset_hash"]:
            raise UnsafeCheckpoint("dataset changed during model dispatch")
        diff = after["completed"] - prior["completed"]
        if diff < 0 or diff > 1:
            raise UnsafeCheckpoint("generation jump or regression detected")
        if prior["phase"] == "AWAITING_PLAN" and (
            diff != 0 or after["phase"] != "AWAITING_DIAGNOSIS"
        ):
            raise UnsafeCheckpoint("plan did not advance to diagnosis exactly once")
        if prior["phase"] == "AWAITING_DIAGNOSIS" and (
            diff != 1
            or after["head_hash"] == prior["head_hash"]
            or after["phase"] not in ("AWAITING_PLAN", "COMPLETED")
        ):
            raise UnsafeCheckpoint("diagnosis did not commit one new unique generation")
        if diff == 1:
            report = raw_after.get("final_report")
            if (
                not isinstance(report, Mapping)
                or report.get("gateway_s7_count_source")
                != "HASH_VERIFIED_IMMUTABLE_GATEWAY_REPORTS"
                or report.get("all_proposed_hypotheses_measured") is not True
            ):
                raise UnsafeCheckpoint("S7 evidence or complete measured hypotheses missing")
        if after["token"] == prior["token"] and after["phase"] != "COMPLETED":
            raise UnsafeCheckpoint("checkpoint token did not rotate")
        prior = after
        if prior["completed"] == target:
            status = "TARGET_REACHED_TEST_ONLY"
            break
    return {
        "schema": "sdk-quant-dispatch-preflight-v1",
        "status": status,
        "session_id": session_id,
        "initial_generations": initial["completed"],
        "completed_generations": prior["completed"],
        "new_generations": prior["completed"] - initial["completed"],
        "official_verified_generations": 0,
        "model_dispatch_attempts": turns,
        "model_provenance": "TEST_ONLY_NO_PROVIDER_ATTESTATION" if turns else "NO_HOST_INVOCATION",
        "orders_enabled": False,
        "independent_oos_approved": False,
    }


def run_sdk_generation_loop(
    service: CheckpointReader,
    *,
    session_id: str,
    target: int,
    host: TestFixtureHost | None = None,
    fixture_mode: bool = False,
    max_dispatches: int = 10,
    lease_state_dir: Path | None = None,
) -> dict[str, Any]:
    """Optionally serialize this local dispatcher; server-side fencing still required."""
    if lease_state_dir is not None:
        with scoped_sdk_run_lease(lease_state_dir, session_id):
            return _run_sdk_generation_loop_unlocked(
                service,
                session_id=session_id,
                target=target,
                host=host,
                fixture_mode=fixture_mode,
                max_dispatches=max_dispatches,
            )
    return _run_sdk_generation_loop_unlocked(
        service,
        session_id=session_id,
        target=target,
        host=host,
        fixture_mode=fixture_mode,
        max_dispatches=max_dispatches,
    )
