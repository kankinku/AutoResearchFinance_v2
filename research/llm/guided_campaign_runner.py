"""Resumable, bounded MCP-only campaign driver around externally GPT-authored plans.

The real language model is the *caller* of this driver. The driver MUST NOT
claim to generate hypotheses or invoke an LLM: it only obtains a fresh plan
through an injected callback, validates the exact checkpoint, and submits to
Guided's immutable, costed executor. Supports multi-step invocation and restart.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from core.integrity.hashes import content_hash


class GuidedService(Protocol):
    state_dir: Path

    def get(self, session_id: str) -> dict[str, Any]: ...
    def submit(self, args: dict[str, Any]) -> dict[str, Any]: ...
    def reconcile(self, session_id: str) -> dict[str, Any]: ...


# Caller must return a fully authored ResearchIntent and GPT research decision.
# An algorithmic or prerecorded callback is useful only for testing, NOT proof
# of live autonomous GPT reasoning.
PlanProvider = Callable[[Mapping[str, Any], tuple[dict[str, str], ...]], dict[str, Any]]


class JournalIntegrityError(ValueError):
    pass


class CampaignPlanError(ValueError):
    pass


@dataclass(frozen=True)
class CampaignResult:
    session_id: str
    requested_generations: int
    completed_generations: int
    newly_completed_generations: int
    attempted_plans: int
    rejected_plans: int
    stop_reason: str
    last_run_id: str | None
    journal_verified_records: int
    orders_enabled: bool = False
    sealed_oos_evaluated: bool = False


class GuidedCampaignRunner:
    """Runs a caller-chosen chunk, never one implicitly unbounded background job."""

    _PLAN_KEYS = frozenset(
        {
            "source_path",
            "intent",
            "research_decision",
            "research_parent_generation",
            "crossover_donor_generation",
        }
    )
    _REPLAN_CODES = (
        "DUPLICATE_STRATEGY",
        "DUPLICATE_EXECUTION_TRACE",
        "STRICT_EXECUTION_UNCHANGED",
        "STRICT_EXECUTION_NO_TRADES",
        "CROSSOVER_NO_NOVEL_SEMANTIC_CHILD",
        "CROSSOVER_INCOMPATIBLE_INDICATOR_DEPENDENCIES",
        "CROSSOVER_NO_SIGNAL_STRUCTURE_DIFFERENCE",
        "CROSSOVER_DONOR_EXIT_UNCHANGED",
    )

    def __init__(self, service: GuidedService) -> None:
        self.service = service
        self.root = Path(service.state_dir).resolve() / "system" / "guided-campaign-journals"

    def _journal_file(self, session_id: str) -> Path:
        if (
            not isinstance(session_id, str)
            or len(session_id) != 32
            or any(c not in "0123456789abcdef" for c in session_id)
        ):
            raise ValueError("invalid campaign session id")
        return self.root / f"{session_id}.jsonl"

    def audit(self, session_id: str) -> list[dict[str, Any]]:
        file = self._journal_file(session_id)
        if not file.exists():
            return []
        if file.is_symlink():
            raise JournalIntegrityError("campaign journal cannot be symlink")
        rows = []
        previous = "GENESIS"
        for line in file.read_text().splitlines():
            try:
                record = json.loads(line)
                checksum = record.pop("record_hash")
                if (
                    record["schema"] != "guided-campaign-journal-v1"
                    or record["session_id"] != session_id
                    or record["sequence"] != len(rows) + 1
                    or record["previous_hash"] != previous
                    or content_hash(record) != checksum
                ):
                    raise JournalIntegrityError("campaign journal chain tampered")
                record["record_hash"] = checksum
                rows.append(record)
                previous = checksum
            except (ValueError, KeyError, TypeError) as error:
                raise JournalIntegrityError("campaign journal unreadable or tampered") from error
        return rows

    def _append(
        self,
        session_id: str,
        *,
        event: str,
        generation: int,
        checkpoint_digest: str | None,
        details: Mapping[str, Any],
    ) -> None:
        file = self._journal_file(session_id)
        self.root.mkdir(parents=True, exist_ok=True)
        history = self.audit(session_id)
        record = {
            "schema": "guided-campaign-journal-v1",
            "session_id": session_id,
            "sequence": len(history) + 1,
            "previous_hash": history[-1]["record_hash"] if history else "GENESIS",
            "event": event,
            "generation": generation,
            "checkpoint_digest": checkpoint_digest,
            "details": dict(details),
        }
        record["record_hash"] = content_hash(record)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
        fd = os.open(file, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            raise

    @staticmethod
    def _plan_payload(checkpoint: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(plan, dict) or not {"source_path", "intent", "research_decision"} <= set(
            plan
        ):
            raise CampaignPlanError("EXTERNAL_GPT_TYPED_PLAN_REQUIRED")
        if set(plan) - GuidedCampaignRunner._PLAN_KEYS:
            raise CampaignPlanError("EXTERNAL_GPT_PLAN_UNKNOWN_FIELDS")
        if not checkpoint.get("adaptive_research_controller"):
            raise CampaignPlanError("CAMPAIGN_REQUIRES_ADAPTIVE_GPT_SESSION")
        if not isinstance(plan["intent"], dict) or not isinstance(plan["research_decision"], dict):
            raise CampaignPlanError("EXTERNAL_GPT_PLAN_NOT_TYPED")
        brief = checkpoint.get("research_director_brief")
        if not isinstance(brief, dict) or plan["research_decision"].get(
            "context_digest"
        ) != brief.get("context_digest"):
            raise CampaignPlanError("EXTERNAL_GPT_PLAN_STALE_CONTEXT")
        if (
            checkpoint.get("status") != "AWAITING_GPT"
            or type(checkpoint.get("generation")) is not int
        ):
            raise CampaignPlanError("CAMPAIGN_NOT_AT_GPT_CHECKPOINT")
        if not isinstance(checkpoint.get("checkpoint_token"), str):
            raise CampaignPlanError("CAMPAIGN_MISSING_CHECKPOINT_TOKEN")
        return {
            "session_id": checkpoint["session_id"],
            "checkpoint_token": checkpoint["checkpoint_token"],
            "generation": checkpoint["generation"],
            **plan,
        }

    def _recover_logged_pending_commit(
        self, session_id: str, checkpoint: Mapping[str, Any]
    ) -> None:
        """If submit finished but the caller crashed before journal append, audit
        the committed run from Guided history. NEVER rerun the evaluator.
        """
        rows = self.audit(session_id)
        if not rows:
            return
        committed = {
            r["generation"]
            for r in rows
            if r["event"] in {"GENERATION_COMMITTED", "RECOVERED_COMMITTED_GENERATION"}
        }
        pending = {r["generation"] for r in rows if r["event"] == "PLAN_RECEIVED"} - committed
        for generation in sorted(pending):
            if generation > checkpoint["completed_generations"]:
                continue
            matches = [
                x for x in checkpoint.get("history", []) if x.get("generation") == generation
            ]
            if len(matches) != 1 or not isinstance(matches[0].get("run_id"), str):
                raise JournalIntegrityError("MISSING_SIGNED_STEP_FOR_CRASH_RECOVERY")
            self._append(
                session_id,
                event="RECOVERED_COMMITTED_GENERATION",
                generation=generation,
                checkpoint_digest=next(
                    (
                        r["checkpoint_digest"]
                        for r in reversed(rows)
                        if r["event"] == "PLAN_RECEIVED" and r["generation"] == generation
                    ),
                    None,
                ),
                details={
                    "run_id": matches[0]["run_id"],
                    "completed_from_original_immutable_history": True,
                    "worker_replayed": False,
                },
            )

    def drive(
        self,
        *,
        session_id: str,
        planner: PlanProvider,
        max_new_generations: int,
        max_replans_per_generation: int = 3,
    ) -> CampaignResult:
        """Hold one per-session OS lock across planning and ALL evaluations.

        The core Guided checkpoint CAS also prevents duplicate jobs. This lock
        additionally prevents two campaign writers from corrupting the audit
        journal or simultaneously requesting different GPT plans.
        """
        file = self._journal_file(session_id)
        self.root.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(str(file) + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("CAMPAIGN_ALREADY_RUNNING") from exc
            return self._drive_unlocked(
                session_id=session_id,
                planner=planner,
                max_new_generations=max_new_generations,
                max_replans_per_generation=max_replans_per_generation,
            )
        finally:
            os.close(lock_fd)

    def _drive_unlocked(
        self,
        *,
        session_id: str,
        planner: PlanProvider,
        max_new_generations: int,
        max_replans_per_generation: int = 3,
    ) -> CampaignResult:
        if not callable(planner):
            raise ValueError("EXTERNAL_GPT_PLAN_PROVIDER_REQUIRED")
        if type(max_new_generations) is not int or not 1 <= max_new_generations <= 100:
            raise ValueError("max_new_generations must be 1..100")
        if type(max_replans_per_generation) is not int or not 0 <= max_replans_per_generation <= 10:
            raise ValueError("max_replans_per_generation must be 0..10")
        self.audit(session_id)  # tampering stops execution before planning
        checkpoint = self.service.get(session_id)
        if (
            checkpoint["session_id"] != session_id
            or checkpoint.get("orders_enabled") is not False
            or checkpoint.get("sealed_oos_evaluated") is not False
        ):
            raise ValueError("UNVERIFIED_OR_UNSAFE_RESEARCH_SESSION")
        if not checkpoint.get("adaptive_research_controller") or not checkpoint.get(
            "require_execution_change"
        ):
            raise ValueError("GUIDED_ADAPTIVE_STRICT_SESSION_REQUIRED")
        self._recover_logged_pending_commit(session_id, checkpoint)
        initial = checkpoint["completed_generations"]
        total = checkpoint["requested_generations"]
        attempts = rejected = 0
        stop = "BUDGET_REACHED"
        while checkpoint["completed_generations"] - initial < max_new_generations:
            status = checkpoint["status"]
            if status == "COMPLETED":
                stop = "TARGET_COMPLETED"
                break
            if status in ("EXECUTING", "INTERRUPTED"):
                # Read-only reconciliation, no replay of already attempted candidate.
                checkpoint = self.service.reconcile(session_id)
                if checkpoint["status"] != "AWAITING_GPT" and checkpoint["status"] != "COMPLETED":
                    stop = "INTERRUPTED_RECONCILIATION_REQUIRED"
                    self._append(
                        session_id,
                        event="HALTED_AMBIGUOUS_EVALUATION",
                        generation=checkpoint["completed_generations"] + 1,
                        checkpoint_digest=None,
                        details={
                            "status": checkpoint["status"],
                            "reconciliation": checkpoint.get("reconciliation"),
                        },
                    )
                    break
                continue
            if status != "AWAITING_GPT":
                stop = "UNEXPECTED_CHECKPOINT_STATUS"
                break
            generation = checkpoint["generation"]
            brief = checkpoint.get("research_director_brief")
            digest = brief.get("context_digest") if isinstance(brief, dict) else None
            failures = []
            for _candidate_attempt in range(max_replans_per_generation + 1):
                # Every rejection returns feedback to the actual planning caller.
                try:
                    plan = planner(checkpoint, tuple(failures))
                    payload = self._plan_payload(checkpoint, plan)
                except Exception as error:
                    self._append(
                        session_id,
                        event="PLANNER_HALTED",
                        generation=generation,
                        checkpoint_digest=digest,
                        details={"error_kind": type(error).__name__, "evaluation_invoked": False},
                    )
                    raise
                attempts += 1
                self._append(
                    session_id,
                    event="PLAN_RECEIVED",
                    generation=generation,
                    checkpoint_digest=digest,
                    details={
                        "plan_hash": content_hash(plan),
                        "research_mode": plan["research_decision"].get("research_mode"),
                        "parent_generation": plan.get("research_parent_generation"),
                        "donor_generation": plan.get("crossover_donor_generation"),
                        "rejected_precommit_count": len(failures),
                    },
                )
                try:
                    submitted = self.service.submit(payload)
                except ValueError as error:
                    reason = str(error)
                    if not reason.startswith(self._REPLAN_CODES):
                        # This is not a harmless rejected precommit. Fail closed.
                        self._append(
                            session_id,
                            event="HARD_STOP",
                            generation=generation,
                            checkpoint_digest=digest,
                            details={"error_kind": type(error).__name__},
                        )
                        raise
                    rejected += 1
                    failures.append(
                        {"code": reason.split(":")[0][:100], "plan_hash": content_hash(plan)}
                    )
                    self._append(
                        session_id,
                        event="PRECOMMIT_REJECTED",
                        generation=generation,
                        checkpoint_digest=digest,
                        details={"code": failures[-1]["code"], "plan_hash": content_hash(plan)},
                    )
                    # Precommit failure must not consume a generation or change token.
                    live = self.service.get(session_id)
                    if (
                        live["completed_generations"] != checkpoint["completed_generations"]
                        or live.get("checkpoint_token") != checkpoint.get("checkpoint_token")
                        or live.get("status") != "AWAITING_GPT"
                    ):
                        raise JournalIntegrityError(
                            "PRECOMMIT_REJECTION_CONSUMED_CHECKPOINT"
                        ) from error
                else:
                    if (
                        submitted["completed_generations"] != generation
                        or submitted.get("last_run_id") is None
                        or submitted.get("status") not in {"COMPLETED", "AWAITING_GPT"}
                        or submitted.get("orders_enabled") is not False
                        or submitted.get("sealed_oos_evaluated") is not False
                    ):
                        raise JournalIntegrityError("SUBMIT_DID_NOT_COMMIT_EXACT_ONE_GENERATION")
                    self._append(
                        session_id,
                        event="GENERATION_COMMITTED",
                        generation=generation,
                        checkpoint_digest=digest,
                        details={
                            "run_id": submitted["last_run_id"],
                            "failed_gate_count": len(submitted.get("previous_failed_gates", [])),
                            "verified_training_controls": submitted.get(
                                "controlled_training_memory", {}
                            ).get("verified_generations"),
                            "verified_two_parent_controls": submitted.get(
                                "controlled_training_memory", {}
                            ).get("two_parent_controls_verified"),
                            "plan_hash": content_hash(plan),
                        },
                    )
                    checkpoint = submitted
                    break
            else:
                stop = "MAX_PRECOMMIT_REPLANS_EXHAUSTED"
                break
        if checkpoint["status"] == "COMPLETED":
            stop = "TARGET_COMPLETED"
        verified = self.audit(session_id)
        return CampaignResult(
            session_id=session_id,
            requested_generations=total,
            completed_generations=checkpoint["completed_generations"],
            newly_completed_generations=checkpoint["completed_generations"] - initial,
            attempted_plans=attempts,
            rejected_plans=rejected,
            stop_reason=stop,
            last_run_id=checkpoint.get("last_run_id"),
            journal_verified_records=len(verified),
        )
