from __future__ import annotations

import hashlib
from typing import Any

from finance_autoresearch.mutation.prompt_builder import MUTABLE_STRATEGY_TARGET_PATH

from .models import ExperimentPlan, KnowledgeSnippet


class HeuristicExperimentPlanner:
    def build_plan(
        self,
        *,
        baseline_evaluation: dict[str, Any],
        latest_experiment: Any = None,
        latest_analysis: Any = None,
        latest_lesson: Any = None,
        knowledge_snippets: list[KnowledgeSnippet] | None = None,
        planner_memory_snapshot: Any = None,
    ) -> ExperimentPlan:
        knowledge_snippets = knowledge_snippets or []
        analysis_output = (
            getattr(latest_analysis, "analysis_output", {}) if latest_analysis else {}
        ) or {}
        latest_metrics = (
            getattr(latest_experiment, "backtest_metrics", {}) if latest_experiment else {}
        ) or {}
        failures = [
            str(item).lower() for item in latest_metrics.get("guardrail_failures", [])
        ]
        analysis_text = " ".join(
            [
                str(analysis_output.get("summary", "")),
                " ".join(str(item) for item in analysis_output.get("weaknesses", [])),
                " ".join(str(item) for item in analysis_output.get("coverage_gaps", [])),
                " ".join(
                    str(item) for item in analysis_output.get("regime_observations", [])
                ),
            ]
        ).lower()
        lesson_statements = self._extract_lesson_statements(latest_lesson)

        experiment_type = "replace_indicator"
        target_problem = "the current indicator mix is not isolating the weakness clearly."
        expected_effect = "Produce a clearer and more stable out-of-sample edge."
        regime_policy = "preserve_current_regime_model"
        planned_mutations: list[dict[str, str]] = [
            {
                "area": "indicator stack",
                "intent": "replace one weak confirmation path instead of stacking another filter",
                "reason": "A targeted indicator swap is easier to audit than broad strategy growth.",
            }
        ]

        if "trade_count" in failures or "undertrading" in analysis_text:
            experiment_type = "simplify_filters"
            target_problem = "trade coverage is too thin and likely over-constrained."
            expected_effect = "Recover trade count without destabilizing exits."
            planned_mutations = [
                {
                    "area": "entry logic",
                    "intent": "remove or relax one confirmation gate",
                    "reason": "Low trade count usually means the strategy is over-filtered.",
                },
                {
                    "area": "indicator stack",
                    "intent": "replace filters instead of stacking new ones",
                    "reason": "This keeps complexity from rising while coverage recovers.",
                },
            ]
        elif "turnover" in failures or "churn" in analysis_text:
            experiment_type = "stabilize_turnover"
            target_problem = "turnover is too high and the strategy is over-trading."
            expected_effect = "Reduce churn while keeping the best directional signals."
            planned_mutations = [
                {
                    "area": "exit logic",
                    "intent": "slow down exit reversal or confirmation",
                    "reason": "Churn usually comes from fragile exits or noisy reversals.",
                },
                {
                    "area": "volatility control",
                    "intent": "prefer a volatility filter if it replaces a noisy clause",
                    "reason": "Volatility filters help when churn comes from noisy sessions.",
                },
            ]
        elif "drawdown" in failures or "drawdown" in analysis_text:
            experiment_type = "tighten_risk"
            target_problem = "downside control is still too weak."
            expected_effect = "Reduce the worst drawdown without removing all exposure."
            planned_mutations = [
                {
                    "area": "stop or exit logic",
                    "intent": "tighten failure exits before changing entries",
                    "reason": "Risk control should improve before expanding trade frequency.",
                }
            ]
        elif any(token in analysis_text for token in ("bull", "bear", "regime")):
            experiment_type = "split_regime"
            target_problem = "bull and bear behavior look mismatched."
            expected_effect = "Let the strategy behave differently across regimes without doubling complexity."
            regime_policy = "consider_split_bull_bear"
            planned_mutations = [
                {
                    "area": "regime routing",
                    "intent": "either simplify the shared logic or split bull and bear rules",
                    "reason": "The analysis points to regime-specific failure modes.",
                }
            ]

        knowledge_text = " ".join(
            " ".join(snippet.tags) + " " + snippet.excerpt.lower()
            for snippet in knowledge_snippets
        )
        if (
            ("atr" in knowledge_text or "rolling_std" in knowledge_text)
            and experiment_type in {"replace_indicator", "stabilize_turnover", "tighten_risk"}
        ):
            planned_mutations.append(
                {
                    "area": "volatility filter",
                    "intent": "use ATR or rolling std only if it replaces a weaker clause",
                    "reason": "The knowledge pack includes volatility-oriented guidance.",
                }
            )
        if "rsi" in knowledge_text and experiment_type == "simplify_filters":
            planned_mutations.append(
                {
                    "area": "thresholds",
                    "intent": "widen RSI thresholds instead of adding another signal",
                    "reason": "The knowledge pack already discusses RSI behavior.",
                }
            )

        hypothesis = self._build_hypothesis(
            experiment_type=experiment_type,
            target_problem=target_problem,
            planned_mutations=planned_mutations,
        )
        plan_summary = (
            f"{target_problem} Focus on {planned_mutations[0]['area']} and keep edits inside "
            "one strategy file."
        )
        guardrails_to_watch = self._guardrails_to_watch(
            baseline_evaluation=baseline_evaluation,
            latest_metrics=latest_metrics,
            analysis_text=analysis_text,
        )
        change_budget = {
            "target_path": MUTABLE_STRATEGY_TARGET_PATH,
            "max_files": 1,
            "max_indicator_count": 4,
            "max_new_conditions": 2,
        }

        return ExperimentPlan(
            hypothesis=hypothesis,
            objective="Beat baseline score by at least 0.05 without triggering guardrail failures.",
            plan_summary=plan_summary,
            experiment_type=experiment_type,
            target_problem=target_problem,
            expected_effect=expected_effect,
            regime_policy=regime_policy,
            change_budget=change_budget,
            guardrails_to_watch=tuple(guardrails_to_watch),
            carry_forward_lessons=tuple(lesson_statements),
            planned_mutations=tuple(planned_mutations),
            knowledge_source_ids=tuple(snippet.source_id for snippet in knowledge_snippets),
        )

    def _build_hypothesis(
        self,
        *,
        experiment_type: str,
        target_problem: str,
        planned_mutations: list[dict[str, str]],
    ) -> str:
        return (
            f"{experiment_type}: {planned_mutations[0]['intent']} because "
            f"{target_problem.rstrip('.')}"
        )

    def _guardrails_to_watch(
        self,
        *,
        baseline_evaluation: dict[str, Any],
        latest_metrics: dict[str, Any],
        analysis_text: str,
    ) -> list[str]:
        guardrails: list[str] = []
        latest_failures = latest_metrics.get("guardrail_failures", [])
        guardrails.extend(str(item) for item in latest_failures)
        if "exposure" in analysis_text:
            guardrails.append("Maintain non-zero exposure for every symbol and regime slice.")
        if "turnover" in analysis_text or "turnover" in str(latest_failures).lower():
            guardrails.append("Keep mean out-of-sample turnover at or below 12.0.")
        if "drawdown" in analysis_text:
            guardrails.append("Keep the worst out-of-sample max drawdown at or below 0.35.")
        if not guardrails:
            if not bool(baseline_evaluation.get("guardrails_passed", True)):
                guardrails.append("Fix the baseline guardrail failure before chasing extra score.")
            else:
                guardrails.append("Preserve guardrail compliance while improving score.")
        return list(dict.fromkeys(guardrails))

    def _extract_lesson_statements(self, latest_lesson: Any) -> list[str]:
        if latest_lesson is None:
            return []
        lesson_output = getattr(latest_lesson, "lesson_output", {}) or {}
        statements: list[str] = []
        seen_statement_hashes: set[str] = set()
        for lesson in lesson_output.get("lessons", []):
            if isinstance(lesson, dict):
                statement = lesson.get("statement")
                if isinstance(statement, str) and statement.strip():
                    normalized = " ".join(statement.strip().lower().split())
                    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                    if digest in seen_statement_hashes:
                        continue
                    seen_statement_hashes.add(digest)
                    statements.append(statement.strip())
                    if len(statements) == 3:
                        return statements
        for action in lesson_output.get("next_actions", []):
            if not isinstance(action, str) or not action.strip():
                continue
            normalized = " ".join(action.strip().lower().split())
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if digest in seen_statement_hashes:
                continue
            seen_statement_hashes.add(digest)
            statements.append(action.strip())
            if len(statements) == 3:
                break
        return statements
