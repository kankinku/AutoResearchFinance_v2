"""P3 opt-in inherited ResearchIntent model loop; default MCP untouched.

The model transport MUST be provided by the caller. No network, paid API,
OpenAI key lookup, broker calls, background jobs, or environment changes here.
Model output is untrusted until S2, precommit P2 risk, S7 and stored evidence
prove it was evaluated. Fail closed, never silently revert to static designs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from core.integrity.hashes import content_hash
from research.llm.diagnostic_research import DiagnosticResponse
from research.llm.director import ResearchIntent


class ResearchModel(Protocol):
    def propose(self, context: dict[str, Any]) -> dict[str, Any]: ...


class P3ResearchError(RuntimeError):
    pass


class ModelProposalAudit:
    """Append-only chained model proposal receipts, no model secrets stored."""

    def __init__(self, path: Path, *, session_id: str, resume: bool = False) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise P3ResearchError("P3 proposal audit must bind a nonempty session ID")
        self.path = path
        self.session_id = session_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.previous_hash: str | None = None
        if resume:
            if not self.path.is_file() or not self.path.stat().st_size:
                raise P3ResearchError("P3 resume requires a nonempty existing audit file")
            with self.path.open(encoding="utf-8") as saved:
                for line in saved:
                    try:
                        receipt = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise P3ResearchError("P3 audit receipt is malformed") from exc
                    if (
                        receipt.get("session_id") != self.session_id
                        or receipt.get("previous_receipt_hash") != self.previous_hash
                        or content_hash({k: v for k, v in receipt.items() if k != "receipt_hash"})
                        != receipt.get("receipt_hash")
                    ):
                        raise P3ResearchError("P3 audit receipt chain or session mismatch")
                    self.previous_hash = receipt["receipt_hash"]
        else:
            try:
                self.path.open("x", encoding="utf-8").close()
            except FileExistsError as exc:
                raise P3ResearchError(
                    "P3 proposal audit path exists; explicit resume required"
                ) from exc

    def append(
        self,
        *,
        phase: str,
        generation: int,
        context: dict[str, Any],
        proposal: dict[str, Any],
        result: str,
        evidence_hash: str | None,
    ) -> None:
        item = {
            "schema": "p3-model-proposal-receipt-v1",
            "session_id": self.session_id,
            "previous_receipt_hash": self.previous_hash,
            "phase": phase,
            "generation": generation,
            "context_hash": content_hash(context),
            "proposal_hash": content_hash(proposal),
            "result": result,
            "source_evidence_hash": evidence_hash,
            "origin": "CALLER_PROVIDED_MODEL_TRANSPORT_NOT_MODEL_ATTESTATION",
            "broker_executable": False,
            "independent_oos_approved": False,
        }
        receipt_hash = content_hash(item)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps({**item, "receipt_hash": receipt_hash}, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())
        self.previous_hash = receipt_hash


class P3InheritedCheckpointAutopilot:
    """Bounded explicit foreground loop for an inherited research session.

    The caller must independently supply a real LLM provider to make this
    actual model research. Mock provider tests are strictly pipeline tests.
    """

    RETRYABLE_PREFIXES = (
        "P2_PRECOMMIT_RISK_REJECTED:",
        "DUPLICATE_INHERITED_STRATEGY:",
        "INTENT_",
        "UNCHANGED_",
        "DUPLICATE_",
    )

    def __init__(
        self,
        service: Any,
        provider: ResearchModel,
        *,
        receipts: ModelProposalAudit,
        max_plan_attempts: int = 12,
    ) -> None:
        if not callable(getattr(provider, "propose", None)):
            raise P3ResearchError("caller-supplied model provider required")
        if type(max_plan_attempts) is not int or not 1 <= max_plan_attempts <= 50:
            raise P3ResearchError("invalid P3 attempt budget")
        self.service = service
        self.provider = provider
        self.receipts = receipts
        self.max_plan_attempts = max_plan_attempts

    def run(self, session_id: str, *, max_generations: int) -> dict[str, Any]:
        if type(max_generations) is not int or not 1 <= max_generations <= 20:
            raise P3ResearchError("max_generations must be 1..20")
        started = self.service.get({"session_id": session_id})
        if started["checkpoint_phase"] not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
            raise P3ResearchError("require safe waiting phase before P3 run")
        if started["orders_enabled"] or started["independent_oos_approved"]:
            raise P3ResearchError("research-only experiment required")
        completed = 0
        planning_proposals = 0
        diagnosis_proposals = 0
        rejected = 0
        while completed < max_generations:
            state = self.service.get({"session_id": session_id})
            if state["checkpoint_phase"] == "COMPLETED":
                break
            if state["checkpoint_phase"] not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
                raise P3ResearchError(
                    "unsafe or interrupted checkpoint; operator reconciliation required"
                )
            if state["orders_enabled"] or state["independent_oos_approved"]:
                raise P3ResearchError("no order/OOS eligible research")
            prior_count = state["completed_generations"]
            generation = prior_count + 1
            prior_evidence = state["history"][-1]["evidence_hash"] if state["history"] else None
            if state["checkpoint_phase"] == "AWAITING_PLAN":
                context = state["model_context"]
                if context.get("output_contract") != "InheritedResearchIntent" or not context.get(
                    "counted_parent_inheritance_ready"
                ):
                    raise P3ResearchError("inherited ResearchIntent contract unavailable")
                accepted = False
                submitted_hashes: set[str] = set()
                previous_model_failure: dict[str, str] | None = None
                for _ in range(self.max_plan_attempts):
                    context = self.service.get({"session_id": session_id})["model_context"]
                    model_context = dict(context)
                    if previous_model_failure is not None:
                        model_context["model_repair_feedback"] = previous_model_failure
                    raw = self.provider.propose(model_context)
                    planning_proposals += 1
                    if not isinstance(raw, dict):
                        raise P3ResearchError("model returned non-object ResearchIntent")
                    proposal_hash = content_hash(raw)
                    if proposal_hash in submitted_hashes:
                        rejected += 1
                        self.receipts.append(
                            phase="PLAN",
                            generation=generation,
                            context=model_context,
                            proposal=raw,
                            result="DUPLICATE_MODEL_PROPOSAL",
                            evidence_hash=prior_evidence,
                        )
                        previous_model_failure = {
                            "reason": "DUPLICATE_MODEL_PROPOSAL",
                            "guidance": "Choose different executable typed operations.",
                        }
                        continue
                    submitted_hashes.add(proposal_hash)
                    try:
                        typed = ResearchIntent.model_validate(raw)
                    except ValidationError:
                        rejected += 1
                        self.receipts.append(
                            phase="PLAN",
                            generation=generation,
                            context=model_context,
                            proposal=raw,
                            result="INVALID_TYPED_PROPOSAL",
                            evidence_hash=prior_evidence,
                        )
                        previous_model_failure = {
                            "reason": "INVALID_TYPED_PROPOSAL",
                            "guidance": "Match the supplied ResearchIntent schema exactly.",
                        }
                        continue
                    if (
                        typed.parent_ids != (context["inherited_parent_strategy_id"],)
                        or not 1 <= len(typed.operations) <= 6
                        or typed.feature_proposal is not None
                        or typed.primitive_request is not None
                    ):
                        raise P3ResearchError(
                            "model plan violated verified parent/operation boundary"
                        )
                    try:
                        staged = self.service.submit_plan(
                            {
                                "session_id": session_id,
                                "checkpoint_token": state["checkpoint_token"],
                                "plan": typed.model_dump(mode="json"),
                                "require_execution_change": True,
                            }
                        )
                    except ValueError as exc:
                        if not str(exc).startswith(self.RETRYABLE_PREFIXES):
                            raise
                        unchanged = self.service.get({"session_id": session_id})
                        if (
                            unchanged["checkpoint_phase"] != "AWAITING_PLAN"
                            or unchanged["completed_generations"] != prior_count
                            or unchanged["checkpoint_token"] != state["checkpoint_token"]
                        ):
                            raise P3ResearchError("risk rejection changed checkpoint") from exc
                        rejected += 1
                        self.receipts.append(
                            phase="PLAN",
                            generation=generation,
                            context=model_context,
                            proposal=raw,
                            result="REJECTED_BY_S2_OR_P2",
                            evidence_hash=prior_evidence,
                        )
                        previous_model_failure = {
                            "reason": "S2_OR_P2_REJECTED",
                            "guidance": (
                                "Review the signed precommit rejection evidence "
                                "and propose distinct operations without relaxing limits."
                            ),
                        }
                        continue
                    self.receipts.append(
                        phase="PLAN",
                        generation=generation,
                        context=model_context,
                        proposal=raw,
                        result="S2_PLAN_STAGED",
                        evidence_hash=prior_evidence,
                    )
                    if staged["checkpoint_phase"] != "AWAITING_DIAGNOSIS":
                        raise P3ResearchError("model plan was not staged for diagnosis")
                    state = staged
                    accepted = True
                    break
                if not accepted:
                    raise P3ResearchError(
                        "MAX_MODEL_PROPOSAL_BUDGET_EXHAUSTED; checkpoint unchanged"
                    )
            context = state["model_context"]
            raw_diagnosis = self.provider.propose(context)
            diagnosis_proposals += 1
            if not isinstance(raw_diagnosis, dict):
                raise P3ResearchError("model returned non-object diagnosis")
            try:
                typed_diagnosis = DiagnosticResponse.model_validate(raw_diagnosis)
            except ValidationError as exc:
                self.receipts.append(
                    phase="DIAGNOSIS",
                    generation=generation,
                    context=context,
                    proposal=raw_diagnosis,
                    result="INVALID_TYPED_DIAGNOSIS",
                    evidence_hash=prior_evidence,
                )
                raise P3ResearchError("model returned invalid typed diagnosis") from exc
            outcome = self.service.submit_diagnosis(
                {
                    "session_id": session_id,
                    "checkpoint_token": state["checkpoint_token"],
                    "diagnosis": typed_diagnosis.model_dump(mode="json"),
                    "require_signal_change": True,
                }
            )
            self.receipts.append(
                phase="DIAGNOSIS",
                generation=generation,
                context=context,
                proposal=raw_diagnosis,
                result="COUNTED_GENERATION_COMMITTED",
                evidence_hash=outcome["history"][-1]["evidence_hash"],
            )
            if outcome["completed_generations"] != prior_count + 1:
                raise P3ResearchError("generation commit count unexpected")
            proof = self.service.evaluate_experiments(
                {
                    "session_id": session_id,
                    "generation": generation,
                }
            )
            current = self.service.get({"session_id": session_id})
            if (
                proof["original_generation_evidence_hash"]
                != current["history"][-1]["evidence_hash"]
                or current["history"][-1]["previous_evidence_hash"] != prior_evidence
            ):
                raise P3ResearchError("S7 / chain proof mismatch")
            completed += 1
        final = self.service.get({"session_id": session_id})
        return {
            "schema": "p3-provider-injected-inherited-loop-v1",
            "mode": "CALLER_PROVIDED_MODEL_TRANSPORT",
            "actual_model_invocation_attested": False,
            "session_id": session_id,
            "new_generations": completed,
            "planning_proposals": planning_proposals,
            "diagnostic_proposals": diagnosis_proposals,
            "typed_proposals_rejected": rejected,
            "receipt_head_hash": self.receipts.previous_hash,
            "completed_generations": final["completed_generations"],
            "research_only": True,
            "independent_oos_approved": False,
            "broker_executable": False,
        }
