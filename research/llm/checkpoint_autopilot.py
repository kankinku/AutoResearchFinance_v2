"""Operator-invoked autonomous GPT checkpoint loop; never a detached daemon.

Model proposals remain untrusted inputs: canonical typed compiler, S2 diagnosis
contract, S7 paired experiments and existing immutable generation checkpoints
are the only authority. No orders/OOS/secret management, no new MCP URL.
"""
from __future__ import annotations

from typing import Any, Protocol

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import AlgorithmPlan
from research.llm.diagnostic_research import DiagnosticResponse


class AutonomousTransport(Protocol):
    """Caller-supplied external LLM: one proposal per independently measured context."""

    def propose(self, context: dict[str, Any]) -> dict[str, Any]: ...


class AutonomousLoopError(ValueError):
    """Refuse unsupported phase, provider response or model-less operation."""


class AcademicCheckpointAutopilot:
    """Complete up to max_generations whole cycles in an explicit foreground call.

    The runner can resume WAITING_PLAN or WAITING_DIAGNOSIS checkpoints
    after client/network interruption without rerunning completed generations.
    RUNNING/INTERRUPTED is not automatically reconciled: operator must first
    establish the prior runner died and call the existing reconciliation flow.
    """

    def __init__(
        self, service: AcademicMCPCheckpointService,
        provider: AutonomousTransport,
    ) -> None:
        self.service = service
        self.provider = provider

    @staticmethod
    def _research_only(state: dict[str, Any]) -> None:
        if (
            state.get("orders_enabled") is not False
            or state.get("independent_oos_approved") is not False
        ):
            raise AutonomousLoopError("research-only checkpoint: order/OOS promotion blocked")

    @staticmethod
    def _verify_s7(
        session_id: str,
        state: dict[str, Any],
        measured: dict[str, Any],
    ) -> int:
        """Fail closed before counting a measured generation as complete."""
        try:
            generation = state["completed_generations"]
            original = state["history"][-1]
            experiments = measured["report"]["experiments"]
            declared = original["hypothesis_ids"]
            if (
                measured.get("session_id") != session_id
                or measured.get("generation") != generation
                or measured.get("original_generation_evidence_hash")
                != original["evidence_hash"]
                or measured.get("study_scope")
                != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
                or measured.get("record_hash")
                != content_hash({k: v for k, v in measured.items() if k != "record_hash"})
                or not isinstance(declared, list)
                or not isinstance(experiments, list)
                or not declared
                or len(experiments) != len(declared)
                or len(set(declared)) != len(declared)
                or sorted(item["hypothesis_id"] for item in experiments)
                != sorted(declared)
            ):
                raise AutonomousLoopError("S7 paired experiment integrity mismatch")
            return len(experiments)
        except (KeyError, TypeError, IndexError) as exc:
            raise AutonomousLoopError("S7 paired experiment evidence is incomplete") from exc

    def run(self, session_id: str, *, max_generations: int) -> dict[str, Any]:
        if type(max_generations) is not int or not 1 <= max_generations <= 100:
            raise AutonomousLoopError("max_generations must be 1..100")
        if not callable(getattr(self.provider, "propose", None)):
            raise AutonomousLoopError("external model provider required")
        completed_here = 0
        proposal_count = 0
        paired_count = 0
        trial_count = 0
        last_measured_generation = 0
        state = self.service.get({"session_id": session_id})
        self._research_only(state)
        if state["status"] in ("INTERRUPTED", "CANCELLED"):
            raise AutonomousLoopError("explicit reconciliation required for stopped session")
        if state["checkpoint_phase"] == "RUNNING":
            raise AutonomousLoopError("existing runner in progress; reconcile after exit")
        while True:
            self._research_only(state)
            if state["completed_generations"]:
                # Separate state store: a process can die after committing the
                # generation but before measuring its hypotheses. Always fill
                # missing S7 evidence BEFORE sending a new plan to the model.
                measured = self.service.evaluate_experiments({
                    "session_id": session_id,
                    "generation": state["completed_generations"],
                })
                verified_trials = self._verify_s7(session_id, state, measured)
                paired_count += 1
                trial_count += verified_trials
                last_measured_generation = state["completed_generations"]
                # The planning context returned by submit_diagnosis was built
                # before S7 measurement. Refresh it after persisting feedback.
                state = self.service.get({"session_id": session_id})
            if state["status"] == "COMPLETED" or completed_here >= max_generations:
                break
            phase = state["checkpoint_phase"]
            if phase not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
                raise AutonomousLoopError("unsupported or interrupted research checkpoint")
            before = state["completed_generations"]
            if phase == "AWAITING_PLAN":
                plan = self.provider.propose(state["model_context"])
                proposal_count += 1
                if not isinstance(plan, dict):
                    raise AutonomousLoopError("external model returned non-object plan")
                typed = AlgorithmPlan.model_validate(plan)
                state = self.service.submit_plan({
                    "session_id": session_id,
                    "checkpoint_token": state["checkpoint_token"],
                    "plan": typed.model_dump(mode="json"),
                })
                if state["checkpoint_phase"] != "AWAITING_DIAGNOSIS":
                    raise AutonomousLoopError("plan did not enter diagnosis checkpoint")
            diagnosis = self.provider.propose(state["model_context"])
            proposal_count += 1
            if not isinstance(diagnosis, dict):
                raise AutonomousLoopError("external model returned non-object diagnosis")
            validated = DiagnosticResponse.model_validate(diagnosis)
            state = self.service.submit_diagnosis({
                "session_id": session_id,
                "checkpoint_token": state["checkpoint_token"],
                "diagnosis": validated.model_dump(mode="json"),
            })
            if state["completed_generations"] != before + 1:
                raise AutonomousLoopError("generation did not commit exactly once")
            completed_here += 1
        if state["completed_generations"] and (
            last_measured_generation != state["completed_generations"]
        ):
            # Do not omit the final completed generation's controlled trial.
            final_report = self.service.evaluate_experiments({
                "session_id": session_id, "generation": state["completed_generations"],
            })
            verified_trials = self._verify_s7(session_id, state, final_report)
            paired_count += 1
            trial_count += verified_trials
        latest = self.service.get({"session_id": session_id})
        self._research_only(latest)
        if (
            latest["status"] == "COMPLETED"
            and (
                not isinstance(latest.get("final_report"), dict)
                or latest["final_report"].get("all_proposed_hypotheses_measured") is not True
            )
        ):
            raise AutonomousLoopError("S7 final report is not fully measured")
        if latest["history"] != state["history"]:
            raise AutonomousLoopError("generation history changed during report")
        return {
            "session_id": session_id,
            "status": latest["status"],
            "completed_generations": latest["completed_generations"],
            "requested_generations": latest["requested_generations"],
            "advanced_generations_this_call": completed_here,
            "external_model_proposals_this_call": proposal_count,
            "controlled_experiments_read_or_executed": paired_count,
            "measured_hypotheses_read_or_executed": trial_count,
            "last_generation_evidence_hash": (
                latest["history"][-1]["evidence_hash"] if latest["history"] else None
            ),
            "final_report": latest["final_report"],
            "model_transport_tested": "CALLER_SUPPLIED_PROVIDER_ONLY",
            "actual_model_invocation_attested": False,
            "broker_executable": False,
            "independent_oos_approved": False,
        }
