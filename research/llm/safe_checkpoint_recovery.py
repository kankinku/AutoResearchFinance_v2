"""Fail-closed, operator-invoked recovery for academic GPT MCP checkpoints.

This code cannot observe/retry a tool call rejected by the host before arrival.
Provider-side policy refusals are never auto-resubmitted; a separate, permitted
user/provider interaction is required. No background worker or trade authority.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.integrity.hashes import content_hash
from research.llm.checkpoint_autopilot import (
    AcademicCheckpointAutopilot,
    AutonomousLoopError,
    DuplicateProposalRetryExceeded,
    OperatorPauseRequested,
)


class TransientProviderFailure(ConnectionError):
    """Trusted provider explicitly reports an interrupted transport."""


class ProviderPolicyRefusal(PermissionError):
    """Provider/host expressly forbids submitting this request."""


class RecoveryAction(str, Enum):
    RETRY_TRANSIENT = "RETRY_TRANSIENT"
    REPAIR_MODEL_OUTPUT = "REPAIR_MODEL_OUTPUT"
    HOLD_POLICY = "HOLD_POLICY"
    HOLD_DUPLICATE_BUDGET = "HOLD_DUPLICATE_BUDGET"
    HOLD_INTEGRITY = "HOLD_INTEGRITY"
    HOLD_UNKNOWN = "HOLD_UNKNOWN"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


class ResearchReviewRequired(AutonomousLoopError):
    """Stop at a persisted checkpoint. No approval or bypass is implied."""

    def __init__(self, action: RecoveryAction, *, session_id: str) -> None:
        self.action = action
        self.session_id = session_id
        super().__init__(f"review required: {action.value} (no automatic resubmission)")


def classify_research_failure(error: BaseException) -> RecoveryAction:
    """Only typed allowlisted failures are recoverable; no message parsing."""
    if isinstance(error, (ProviderPolicyRefusal, PermissionError)):
        return RecoveryAction.HOLD_POLICY
    if isinstance(error, DuplicateProposalRetryExceeded):
        return RecoveryAction.HOLD_DUPLICATE_BUDGET
    if isinstance(error, TransientProviderFailure):
        return RecoveryAction.RETRY_TRANSIENT
    if isinstance(error, ValidationError):
        return RecoveryAction.REPAIR_MODEL_OUTPUT
    if isinstance(error, (AutonomousLoopError, AssertionError)):
        return RecoveryAction.HOLD_INTEGRITY
    return RecoveryAction.HOLD_UNKNOWN


class RecoveryAuditJournal:
    """Minimal, append-only owner-only log. No proposal, token or secrets stored."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(
        self,
        *,
        session_id: str,
        phase: str,
        completed: int,
        decision: RecoveryAction,
        failure_type: str,
        attempt: int,
        checkpoint_fingerprint: str,
    ) -> None:
        if (
            len(session_id) != 32 or not all(c in "0123456789abcdef" for c in session_id)
            or phase not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS", "RUNNING", "INTERRUPTED")
            or completed < 0 or attempt < 0
            or len(checkpoint_fingerprint) != 64
        ):
            raise ResearchReviewRequired(RecoveryAction.HOLD_INTEGRITY, session_id=session_id)
        record = {
            "schema": "academic-t4-safe-recovery-v1",
            "session_id": session_id,
            "phase": phase,
            "completed_generations": completed,
            "decision": decision.value,
            "failure_type": failure_type[:90],
            "attempt": attempt,
            "checkpoint_fingerprint": checkpoint_fingerprint,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "orders_enabled": False,
            "host_policy_override": False,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ResearchReviewRequired(RecoveryAction.HOLD_INTEGRITY, session_id=session_id)
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags, 0o600)
        try:
            if os.fstat(fd).st_mode & 0o077:
                raise ResearchReviewRequired(
                    RecoveryAction.HOLD_INTEGRITY, session_id=session_id,
                )
            with os.fdopen(fd, "a", encoding="utf-8", closefd=False) as stream:
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)


class SafeCheckpointRecoveryController:
    """Re-run bounded foreground autopilot only after independent state verification.

    It retries *only* typed transient-provider exceptions or a locally detected
    typed model schema failure. Unclassified, policy and integrity failures hold.
    There is no generic safety-filter retry and no hidden bypass transport.
    """

    def __init__(
        self,
        autopilot: AcademicCheckpointAutopilot,
        *,
        audit_path: Path,
        max_transport_retries: int = 2,
        max_schema_repairs: int = 1,
        pause: Callable[[float], None] | None = None,
    ) -> None:
        if type(max_transport_retries) is not int or not 0 <= max_transport_retries <= 2:
            raise ValueError("transport retries must be 0..2")
        if type(max_schema_repairs) is not int or not 0 <= max_schema_repairs <= 1:
            raise ValueError("schema repairs must be 0..1")
        self.autopilot = autopilot
        self.journal = RecoveryAuditJournal(audit_path)
        self.max_transport_retries = max_transport_retries
        self.max_schema_repairs = max_schema_repairs
        self.pause = pause or (lambda _: None)

    @staticmethod
    def _fingerprint(state: dict[str, Any]) -> str:
        return content_hash({
            "session_id": state["session_id"],
            "phase": state["checkpoint_phase"],
            "completed": state["completed_generations"],
            "last_generation_hash": (
                state["history"][-1]["evidence_hash"] if state["history"] else None
            ),
            "context_hash": state.get("model_context", {}).get("context_hash"),
        })

    @staticmethod
    def _verify_transition(
        before: dict[str, Any], after: dict[str, Any],
        *, max_advance: int,
    ) -> None:
        if (
            before["session_id"] != after["session_id"]
            or before["dataset_hash"] != after["dataset_hash"]
            or before["requested_generations"] != after["requested_generations"]
            or before["orders_enabled"] is not False
            or after["orders_enabled"] is not False
            or after["independent_oos_approved"] is not False
            or after["completed_generations"] < before["completed_generations"]
            or after["completed_generations"] > before["completed_generations"] + max_advance
            or after["history"][:len(before["history"])] != before["history"]
            or len(after["history"]) != after["completed_generations"]
            or not (
                after["checkpoint_phase"] in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS")
                or (
                    after["checkpoint_phase"] == "COMPLETED"
                    and after["status"] == "COMPLETED"
                    and after["completed_generations"] == after["requested_generations"]
                )
            )
        ):
            raise AutonomousLoopError("untrusted recovery checkpoint transition")
        # A lost reply might have committed one generation. Its S7 must exist
        # and match the immutable evidence before another model proposal.
        if after["completed_generations"] > before["completed_generations"]:
            if after["checkpoint_phase"] not in ("AWAITING_PLAN", "COMPLETED"):
                raise AutonomousLoopError("committed generation without next plan checkpoint")

    def run(self, session_id: str, *, max_generations: int) -> dict[str, Any]:
        if type(max_generations) is not int or not 1 <= max_generations <= 100:
            raise ValueError("max_generations must be 1..100")
        baseline = self.autopilot.service.get({"session_id": session_id})
        if baseline["checkpoint_phase"] not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
            raise ResearchReviewRequired(RecoveryAction.HOLD_INTEGRITY, session_id=session_id)
        original_completed = baseline["completed_generations"]
        limits = {
            RecoveryAction.RETRY_TRANSIENT: self.max_transport_retries,
            RecoveryAction.REPAIR_MODEL_OUTPUT: self.max_schema_repairs,
        }
        attempts: dict[RecoveryAction, int] = {}
        while True:
            current = self.autopilot.service.get({"session_id": session_id})
            self._verify_transition(baseline, current, max_advance=max_generations)
            remaining = max_generations - (current["completed_generations"] - original_completed)
            if remaining <= 0:
                return {
                    "session_id": session_id,
                    "completed_generations": current["completed_generations"],
                    "requested_generations": current["requested_generations"],
                    "advanced_generations_this_call": max_generations,
                    "status": current["status"],
                    "broker_executable": False,
                    "independent_oos_approved": False,
                }
            try:
                result = self.autopilot.run(session_id, max_generations=remaining)
                self._verify_completed_result(current, result)
                return result
            except OperatorPauseRequested:
                # Operator control cannot be treated as retryable model failure.
                raise
            except Exception as exc:
                decision = classify_research_failure(exc)
                # Read the authoritative state before interpreting a lost reply.
                try:
                    latest = self.autopilot.service.get({"session_id": session_id})
                    self._verify_transition(current, latest, max_advance=remaining)
                    self._verify_history_prefix(baseline, latest)
                except Exception as state_exc:
                    raise ResearchReviewRequired(
                        RecoveryAction.HOLD_INTEGRITY, session_id=session_id,
                    ) from state_exc
                attempts[decision] = attempts.get(decision, 0) + 1
                allowed = attempts[decision] <= limits.get(decision, 0)
                reported = decision if allowed else (
                    RecoveryAction.RETRY_EXHAUSTED if decision in limits
                    else decision
                )
                self.journal.append(
                    session_id=session_id,
                    phase=latest["checkpoint_phase"],
                    completed=latest["completed_generations"],
                    decision=reported,
                    failure_type=type(exc).__name__,
                    attempt=attempts[decision],
                    checkpoint_fingerprint=self._fingerprint(latest),
                )
                if not allowed:
                    raise ResearchReviewRequired(reported, session_id=session_id) from exc
                baseline = latest
                self.pause(min(2 ** (attempts[decision] - 1), 4))

    @staticmethod
    def _verify_history_prefix(
        before: dict[str, Any], after: dict[str, Any],
    ) -> None:
        if (
            after["history"][:len(before["history"])] != before["history"]
            or before["dataset_hash"] != after["dataset_hash"]
            or before["requested_generations"] != after["requested_generations"]
            or after["orders_enabled"] is not False
        ):
            raise AutonomousLoopError("unexpected immutable research history rewrite")

    @staticmethod
    def _verify_completed_result(
        before: dict[str, Any], result: dict[str, Any],
    ) -> None:
        if (
            result.get("broker_executable") is not False
            or result.get("independent_oos_approved") is not False
            or result["completed_generations"] < before["completed_generations"]
        ):
            raise AutonomousLoopError("untrusted research completion response")
