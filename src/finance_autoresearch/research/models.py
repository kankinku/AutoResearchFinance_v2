from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class KnowledgeSnippet:
    source_id: str
    title: str
    source_path: str
    sha256: str
    excerpt: str
    tags: tuple[str, ...] = ()
    relevance_reason: str = ""
    score: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_path": self.source_path,
            "sha256": self.sha256,
            "excerpt": self.excerpt,
            "tags": list(self.tags),
            "relevance_reason": self.relevance_reason,
            "score": self.score,
        }


@dataclass(slots=True, frozen=True)
class ExperimentPlan:
    hypothesis: str
    objective: str
    plan_summary: str
    experiment_type: str
    target_problem: str
    expected_effect: str
    regime_policy: str
    change_budget: dict[str, Any]
    guardrails_to_watch: tuple[str, ...] = ()
    carry_forward_lessons: tuple[str, ...] = ()
    planned_mutations: tuple[dict[str, str], ...] = ()
    knowledge_source_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "objective": self.objective,
            "plan_summary": self.plan_summary,
            "experiment_type": self.experiment_type,
            "target_problem": self.target_problem,
            "expected_effect": self.expected_effect,
            "regime_policy": self.regime_policy,
            "change_budget": dict(self.change_budget),
            "guardrails_to_watch": list(self.guardrails_to_watch),
            "carry_forward_lessons": list(self.carry_forward_lessons),
            "planned_mutations": [dict(item) for item in self.planned_mutations],
            "knowledge_source_ids": list(self.knowledge_source_ids),
        }


@dataclass(slots=True, frozen=True)
class LessonCard:
    decision: str
    summary: str
    referenced_plan_summary: str
    lessons: tuple[dict[str, Any], ...] = ()
    next_actions: tuple[str, ...] = ()
    knowledge_source_ids: tuple[str, ...] = ()
    supporting_signals: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "summary": self.summary,
            "referenced_plan_summary": self.referenced_plan_summary,
            "lessons": [dict(item) for item in self.lessons],
            "next_actions": list(self.next_actions),
            "knowledge_source_ids": list(self.knowledge_source_ids),
            "supporting_signals": dict(self.supporting_signals),
        }


@dataclass(slots=True, frozen=True)
class PlannerMemorySnapshot:
    history_window: int
    family_counts: dict[str, int]
    family_cooldowns: tuple[str, ...] = ()
    repeated_failure_signals: tuple[str, ...] = ()
    carry_forward_lessons: tuple[str, ...] = ()
    linked_note_paths: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "history_window": self.history_window,
            "family_counts": dict(self.family_counts),
            "family_cooldowns": list(self.family_cooldowns),
            "repeated_failure_signals": list(self.repeated_failure_signals),
            "carry_forward_lessons": list(self.carry_forward_lessons),
            "linked_note_paths": list(self.linked_note_paths),
        }


@dataclass(slots=True, frozen=True)
class ResearchBrief:
    hypothesis: str
    objective: str
    plan_summary: str
    family: str
    target_problem: str
    expected_effect: str
    regime_policy: str
    complexity_budget: dict[str, Any]
    historical_risks: tuple[str, ...] = ()
    guardrails_to_watch: tuple[str, ...] = ()
    carry_forward_lessons: tuple[str, ...] = ()
    planned_mutations: tuple[dict[str, str], ...] = ()
    artifact_mode: str = "prefer_genome"
    allowed_indicator_pool: tuple[str, ...] = ()
    knowledge_evidence: tuple[dict[str, Any], ...] = ()
    knowledge_source_ids: tuple[str, ...] = ()

    @property
    def experiment_type(self) -> str:
        return self.family

    @property
    def change_budget(self) -> dict[str, Any]:
        return dict(self.complexity_budget)

    def to_payload(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "objective": self.objective,
            "plan_summary": self.plan_summary,
            "family": self.family,
            "experiment_type": self.family,
            "target_problem": self.target_problem,
            "expected_effect": self.expected_effect,
            "regime_policy": self.regime_policy,
            "complexity_budget": dict(self.complexity_budget),
            "historical_risks": list(self.historical_risks),
            "guardrails_to_watch": list(self.guardrails_to_watch),
            "carry_forward_lessons": list(self.carry_forward_lessons),
            "planned_mutations": [dict(item) for item in self.planned_mutations],
            "artifact_mode": self.artifact_mode,
            "allowed_indicator_pool": list(self.allowed_indicator_pool),
            "knowledge_evidence": [dict(item) for item in self.knowledge_evidence],
            "knowledge_source_ids": list(self.knowledge_source_ids),
        }
