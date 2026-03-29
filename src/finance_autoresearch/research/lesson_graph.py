from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ExperimentPlan, KnowledgeSnippet, ResearchBrief


@dataclass(slots=True, frozen=True)
class LessonGraphDraft:
    thesis: str
    mutation_delta: str
    observed_outcome: str
    failure_mode: str
    next_action: str
    confidence: str
    novelty_score: float
    knowledge_source_ids: tuple[str, ...]


def build_lesson_graph(
    *,
    research_plan: ExperimentPlan | ResearchBrief,
    decision: str,
    knowledge_snippets: list[KnowledgeSnippet],
    candidate_evaluation: dict[str, Any],
    analysis_output: dict[str, Any],
) -> LessonGraphDraft:
    next_actions = tuple(
        str(item).strip()
        for item in analysis_output.get("next_hypothesis_hints", [])
        if str(item).strip()
    )
    guardrail_failures = tuple(
        str(item).strip()
        for item in candidate_evaluation.get("guardrail_failures", [])
        if str(item).strip()
    )
    return LessonGraphDraft(
        thesis=research_plan.hypothesis,
        mutation_delta=research_plan.plan_summary,
        observed_outcome=decision,
        failure_mode=_failure_mode(decision=decision, guardrail_failures=guardrail_failures, analysis_output=analysis_output),
        next_action=next_actions[0] if next_actions else research_plan.target_problem,
        confidence="high" if decision == "keep" else "medium",
        novelty_score=1.0 if decision == "keep" else 0.5,
        knowledge_source_ids=tuple(snippet.source_id for snippet in knowledge_snippets),
    )


def _failure_mode(
    *,
    decision: str,
    guardrail_failures: tuple[str, ...],
    analysis_output: dict[str, Any],
) -> str:
    if decision == "keep":
        return "kept"
    if guardrail_failures:
        return guardrail_failures[0]
    weaknesses = analysis_output.get("weaknesses", [])
    if weaknesses:
        return str(weaknesses[0])
    return "score_shortfall"
