"""Evidence-gated diagnostic planning for a future autonomous research director.

S2 only: this module neither places orders nor executes proposed experiments.
LLM text is always an UNTESTED hypothesis, even if a safe typed IR mutation
is preflighted. It uses the existing immutable evaluator and intent bridge.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from experiments.identity import semantic_strategy_hash
from research.indicator_engine.decision_audit import (
    AcademicDecisionAudit,
    calculate_audit_hash,
)
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import IntentEligibilityError, apply_intent
from strategy_ir.schema import StrategyIR

# One executable S7 metric contract shared with the gateway and experiment engine.
# Win rate and profit factor still require round-trip semantics not uniformly
# available from every supported inherited replay; do not advertise them.
SUPPORTED_S7_METRICS = (
    "total_return", "cagr", "max_drawdown", "sharpe", "sortino",
    "trade_count", "exposure",
)


class DiagnosisContractError(ValueError):
    """Reject unverifiable LLM diagnoses and malformed evidence without executing."""


class DiagnosticProvider(Protocol):
    def propose(self, context: dict[str, Any]) -> dict[str, Any]: ...


class ExperimentHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = Field(min_length=3, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    observed_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    mechanism: str = Field(min_length=12, max_length=1200)
    alternative: str = Field(min_length=12, max_length=1200)
    expected_metric: Literal[
        "total_return", "cagr", "max_drawdown", "sharpe", "sortino",
        "trade_count", "exposure",
    ]
    predicted_direction: Literal["INCREASE", "DECREASE"]
    test_design: Literal["ABLATION", "PARAMETER", "RULE_STRUCTURE", "REGIME"]
    control: Literal["PARENT_UNCHANGED"]
    next_intent: ResearchIntent

    @model_validator(mode="after")
    def check_experiment_shape(self) -> ExperimentHypothesis:
        if len(set(self.observed_ids)) != len(self.observed_ids):
            raise ValueError("duplicate evidence observation IDs")
        if not 1 <= len(self.next_intent.operations) <= 6:
            raise ValueError("diagnostic experiments require 1-6 typed operations")
        return self


class DiagnosticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_hash: str = Field(min_length=64, max_length=64)
    audit_hash: str = Field(min_length=64, max_length=64)
    strategy_hash: str = Field(min_length=64, max_length=64)
    dataset_hash: str = Field(min_length=64, max_length=64)
    summary: str = Field(min_length=12, max_length=1600)
    hypotheses: tuple[ExperimentHypothesis, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_hypotheses(self) -> DiagnosticResponse:
        if len({h.hypothesis_id for h in self.hypotheses}) != len(self.hypotheses):
            raise ValueError("duplicate hypothesis IDs")
        return self


@dataclass(frozen=True)
class ProposedExperiment:
    hypothesis_id: str
    observed_ids: tuple[str, ...]
    parent_id: str
    mechanism: str
    alternative: str
    control: Literal["PARENT_UNCHANGED"]
    proposed_intent: ResearchIntent
    test_design: str
    expected_metric: str
    predicted_direction: str
    child: StrategyIR
    child_hash: str
    causal_status: Literal["UNTESTED_HYPOTHESIS"] = "UNTESTED_HYPOTHESIS"
    independent_oos_approved: Literal[False] = False


@dataclass(frozen=True)
class ValidatedDiagnosticPlan:
    audit_hash: str
    context_hash: str
    proposal_hash: str
    analysis_summary: str
    experiments: tuple[ProposedExperiment, ...]
    status: Literal[
        "VALIDATED_PROPOSAL_REQUIRES_EXPERIMENT"
    ] = "VALIDATED_PROPOSAL_REQUIRES_EXPERIMENT"
    causal_claim: Literal["UNTESTED_HYPOTHESIS"] = "UNTESTED_HYPOTHESIS"
    independent_oos_approved: Literal[False] = False
    broker_executable: Literal[False] = False


def _verify_audit(audit: AcademicDecisionAudit, parent: StrategyIR) -> None:
    if (
        audit.status != "RESEARCH_DECISION_AUDIT_ONLY"
        or audit.candidate_promotable is not False
        or audit.broker_executable is not False
        or audit.point_in_time_verified is not False
        or audit.llm_packet.get("audit_hash") != audit.trace_hash
        or audit.trace_hash != calculate_audit_hash(
            audit.evaluation, audit.decisions, audit.fills, audit.round_trips,
            audit.llm_packet,
        )
        or content_hash(audit.evaluation.equity_curve) != audit.evaluation.equity_hash
        or audit.evaluation.final_equity != audit.evaluation.equity_curve[-1]
    ):
        raise DiagnosisContractError("audit evidence is unverified or tampered")
    parent_hash = content_hash(parent.model_dump(mode="json", by_alias=True))
    if parent_hash != audit.evaluation.strategy_hash:
        raise DiagnosisContractError("strategy identity does not match audited strategy")
    if audit.evaluation.dataset_hash != audit.llm_packet.get("dataset_hash"):
        raise DiagnosisContractError("audit dataset binding mismatch")


def build_diagnostic_context(
    audit: AcademicDecisionAudit, parent: StrategyIR,
) -> dict[str, Any]:
    """Provide measured facts and evidence IDs, not invented LLM causal labels."""
    _verify_audit(audit, parent)
    packet = deepcopy(audit.llm_packet)
    context: dict[str, Any] = {
        "schema": "research-diagnostic-context-v1",
        "audit_hash": audit.trace_hash,
        "strategy_hash": audit.evaluation.strategy_hash,
        "dataset_hash": audit.evaluation.dataset_hash,
        "algorithm_parent_id": parent.strategy_id,
        "available_indicator_aliases": sorted((*parent.indicators, *parent.features)),
        "metrics": packet["metrics"],
        "observations": {
            "loss_cases": packet["loss_examples"],
            "execution_samples": packet["execution_samples"],
            "decision_count": packet["decision_count"],
            "fill_count": packet["fill_count"],
            "closed_trades": packet["closed_trades"],
            "paid_transaction_costs": packet["paid_transaction_costs"],
            "remaining_execution_samples": packet["more_execution_samples"],
        },
        "causal_status": "NOT_ESTABLISHED",
        "execution_policy": "PROPOSE_ONLY_NO_ORDER_OR_APPROVAL",
        "validation_scope": "REUSED_DEVELOPMENT_NON_PIT_NO_INDEPENDENT_OOS",
    }
    # A valid zero-fill strategy has no trade_id/fill_id to cite, but requiring
    # every diagnosis to cite one would deadlock a multi-generation GPT cycle.
    # Instead expose a bounded, deterministic sample of ALREADY HASH-BOUND
    # decisions where nothing executed. Never fabricate trades or change the
    # existing signed audit packet or nonzero-run context hashes.
    if not audit.fills:
        eligible = [
            decision for decision in audit.decisions
            if decision.action in {"WARMUP", "FILTERED_REGIME", "NO_ENTRY_SIGNAL"}
            and decision.fill_id is None
        ]
        limit = min(12, len(eligible))
        chosen = (
            [eligible[(i * (len(eligible) - 1)) // (limit - 1)]
             for i in range(limit)]
            if limit > 1 else eligible[:1]
        )
        context["observations"]["non_execution_decision_samples"] = [
            {
                "decision_id": item.decision_id,
                "signal_time": item.signal_time.isoformat(),
                "decision_action": item.action,
                "entry_signal": item.entry_signal,
                "regime_signal": item.regime_signal,
                "evaluated_gates": dict(item.evaluated_gates),
                "indicator_values": dict(item.indicator_values),
                "fill_id": None,
            }
            for item in chosen
        ]
    context["context_hash"] = content_hash(context)
    return context


def approve_diagnostic_plan(
    audit: AcademicDecisionAudit,
    parent: StrategyIR,
    context: dict[str, Any],
    raw_response: dict[str, Any],
) -> ValidatedDiagnosticPlan:
    """Check LLM evidence references + existing IR gate; never execute/PROMOTE."""
    trusted = build_diagnostic_context(audit, parent)
    if context != trusted:
        raise DiagnosisContractError("audit context was changed after compilation")
    try:
        response = DiagnosticResponse.model_validate(raw_response)
    except ValidationError as exc:
        raise DiagnosisContractError("invalid diagnostic response schema") from exc
    if (
        response.context_hash != trusted["context_hash"]
        or response.audit_hash != audit.trace_hash
        or response.strategy_hash != audit.evaluation.strategy_hash
        or response.dataset_hash != audit.evaluation.dataset_hash
    ):
        raise DiagnosisContractError("diagnostic evidence identities are stale or mismatched")
    observations = trusted["observations"]
    loss_cases = observations["loss_cases"]
    execution_samples = observations["execution_samples"]
    allowed_ids = {
        *(
            value
            for item in loss_cases
            for value in (
                item["trade_id"], item["entry_decision_id"], item["exit_decision_id"]
            )
        ),
        *(
            value
            for item in execution_samples
            for value in (item["trade_id"], item["decision_id"], item["fill_id"])
        ),
    }
    # Zero-fill research can reference only actual audited, non-executing
    # decisions that the service made available to the model. These IDs are
    # authenticated by _verify_audit's full decision trace hash, and any
    # fabricated ID or modified model context is rejected above.
    allowed_ids.update(
        item["decision_id"]
        for item in observations.get("non_execution_decision_samples", ())
    )
    plans: list[ProposedExperiment] = []
    seen_children: set[str] = set()
    parent_semantic = semantic_strategy_hash(parent)
    # Use only the registry the real research worker already consumes.
    feature_specs = research_feature_specs()
    for hypothesis in response.hypotheses:
        if any(ref not in allowed_ids for ref in hypothesis.observed_ids):
            raise DiagnosisContractError("diagnostic refers to unknown audit observation")
        intent = hypothesis.next_intent
        if intent.parent_ids != (parent.strategy_id,):
            raise DiagnosisContractError("diagnostic parent is unrelated to audited strategy")
        if intent.primitive_request is not None or intent.feature_proposal is not None:
            raise DiagnosisContractError("unverified indicator/primitive cannot enter experiment")
        try:
            child = apply_intent(parent, intent, feature_specs)
        except (ValueError, IntentEligibilityError) as exc:
            raise DiagnosisContractError("diagnostic intent fails verified mutation gate") from exc
        if child.strategy_id != parent.strategy_id:
            raise DiagnosisContractError("diagnostic cannot replace strategy identity")
        child_hash = content_hash(child.model_dump(mode="json", by_alias=True))
        child_semantic = semantic_strategy_hash(child)
        if child_semantic == parent_semantic or child_semantic in seen_children:
            raise DiagnosisContractError("duplicate or unchanged diagnostic proposal")
        seen_children.add(child_semantic)
        plans.append(ProposedExperiment(
            hypothesis_id=hypothesis.hypothesis_id,
            observed_ids=hypothesis.observed_ids,
            parent_id=parent.strategy_id,
            mechanism=hypothesis.mechanism,
            alternative=hypothesis.alternative,
            control=hypothesis.control,
            proposed_intent=intent,
            test_design=hypothesis.test_design,
            expected_metric=hypothesis.expected_metric,
            predicted_direction=hypothesis.predicted_direction,
            child=child,
            child_hash=child_hash,
        ))
    return ValidatedDiagnosticPlan(
        audit_hash=audit.trace_hash,
        context_hash=str(trusted["context_hash"]),
        proposal_hash=content_hash(response.model_dump(mode="json")),
        analysis_summary=response.summary,
        experiments=tuple(plans),
    )


def diagnose_with_provider(
    audit: AcademicDecisionAudit,
    parent: StrategyIR,
    provider: DiagnosticProvider,
) -> ValidatedDiagnosticPlan:
    """One typed LLM checkpoint, ready for later durable generational orchestration."""
    context = build_diagnostic_context(audit, parent)
    raw = provider.propose(deepcopy(context))
    if not isinstance(raw, dict):
        raise DiagnosisContractError("diagnostic provider must return structured object")
    return approve_diagnostic_plan(audit, parent, context, raw)
