from __future__ import annotations

from typing import Any

from .models import ExperimentPlan, KnowledgeSnippet, LessonCard


class LessonBuilder:
    def build(
        self,
        *,
        plan: ExperimentPlan,
        decision: str,
        candidate_evaluation: dict[str, Any],
        analysis_output: dict[str, Any],
        knowledge_snippets: list[KnowledgeSnippet] | None = None,
    ) -> LessonCard:
        knowledge_snippets = knowledge_snippets or []
        guardrail_failures = [
            str(item) for item in candidate_evaluation.get("guardrail_failures", [])
        ]
        lessons: list[dict[str, Any]] = []
        if decision == "keep":
            lessons.append(
                {
                    "category": "accepted-change",
                    "statement": "The planned mutation cleared guardrails and improved enough to keep.",
                    "evidence": ["decision", "analysis.summary"],
                    "confidence": "high",
                }
            )
        if guardrail_failures:
            lessons.append(
                {
                    "category": "guardrail",
                    "statement": "Preserve guardrail compliance before optimizing for extra score.",
                    "evidence": ["guardrail_failures", "analysis.weaknesses"],
                    "confidence": "high",
                }
            )
        first_gap = next(iter(analysis_output.get("coverage_gaps", [])), None)
        if isinstance(first_gap, str) and first_gap.strip():
            lessons.append(
                {
                    "category": "coverage",
                    "statement": first_gap.strip(),
                    "evidence": ["analysis.coverage_gaps"],
                    "confidence": "medium",
                }
            )
        if not lessons:
            lessons.append(
                {
                    "category": "iteration",
                    "statement": analysis_output.get("summary", plan.plan_summary),
                    "evidence": ["analysis.summary"],
                    "confidence": "medium",
                }
            )
        next_actions = [
            str(item) for item in analysis_output.get("next_hypothesis_hints", []) if str(item).strip()
        ]
        if not next_actions:
            next_actions = [plan.target_problem]
        return LessonCard(
            decision=decision,
            summary=str(analysis_output.get("summary", plan.plan_summary)),
            referenced_plan_summary=plan.plan_summary,
            lessons=tuple(lessons),
            next_actions=tuple(next_actions[:3]),
            knowledge_source_ids=tuple(snippet.source_id for snippet in knowledge_snippets),
            supporting_signals={
                "score": candidate_evaluation.get("score"),
                "guardrail_failures": guardrail_failures,
                "experiment_type": plan.experiment_type,
            },
        )
