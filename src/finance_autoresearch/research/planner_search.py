from __future__ import annotations

from typing import Any

from finance_autoresearch.mutation.prompt_builder import MUTABLE_STRATEGY_TARGET_PATH

from .knowledge_catalog import (
    allowed_indicator_pool,
    knowledge_context_signals,
    knowledge_evidence,
)
from .models import KnowledgeSnippet, PlannerMemorySnapshot, ResearchBrief


class ResearchScheduler:
    def build_plan(
        self,
        *,
        baseline_evaluation: dict[str, Any],
        latest_experiment: Any = None,
        latest_analysis: Any = None,
        latest_lesson: Any = None,
        knowledge_snippets: list[KnowledgeSnippet] | None = None,
        planner_memory_snapshot: PlannerMemorySnapshot | None = None,
    ) -> ResearchBrief:
        knowledge_snippets = knowledge_snippets or []
        planner_memory_snapshot = planner_memory_snapshot or PlannerMemorySnapshot(
            history_window=0,
            family_counts={},
        )
        analysis_output = (
            getattr(latest_analysis, "analysis_output", {}) if latest_analysis else {}
        ) or {}
        latest_metrics = (
            getattr(latest_experiment, "backtest_metrics", {}) if latest_experiment else {}
        ) or {}
        failures = [str(item).lower() for item in latest_metrics.get("guardrail_failures", [])]
        analysis_text = " ".join(
            [
                str(analysis_output.get("summary", "")),
                " ".join(str(item) for item in analysis_output.get("weaknesses", [])),
                " ".join(str(item) for item in analysis_output.get("coverage_gaps", [])),
                " ".join(str(item) for item in analysis_output.get("regime_observations", [])),
            ]
        ).lower()

        family = "replace_indicator"
        target_problem = "the current indicator mix is not isolating the weakness clearly."
        expected_effect = "Produce a clearer and more stable out-of-sample edge."
        regime_policy = "preserve_current_regime_model"
        artifact_mode = "prefer_genome"
        planned_mutations: list[dict[str, str]] = [
            {
                "area": "indicator stack",
                "intent": "replace one weak confirmation path instead of stacking another filter",
                "reason": "A targeted indicator swap is easier to audit than broad strategy growth.",
            }
        ]

        if "trade_count" in failures or "undertrading" in analysis_text:
            family = "simplify_filters"
            target_problem = "trade coverage is too thin and likely over-constrained."
            expected_effect = "Recover trade count without destabilizing exits."
            planned_mutations = [
                {
                    "area": "entry logic",
                    "intent": "remove or relax one confirmation gate",
                    "reason": "Low trade count usually means the strategy is over-filtered.",
                }
            ]
        elif "turnover" in failures or "churn" in analysis_text:
            family = "stabilize_turnover"
            target_problem = "turnover is too high and the strategy is over-trading."
            expected_effect = "Reduce churn while keeping the best directional signals."
            planned_mutations = [
                {
                    "area": "exit logic",
                    "intent": "slow down exit reversal or confirmation",
                    "reason": "Churn usually comes from fragile exits or noisy reversals.",
                }
            ]
        elif "drawdown" in failures or "drawdown" in analysis_text:
            family = "tighten_risk"
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
            family = "split_regime"
            target_problem = "bull and bear behavior look mismatched."
            expected_effect = "Let the strategy behave differently across regimes without doubling complexity."
            regime_policy = "consider_split_bull_bear"
            artifact_mode = "prefer_raw"
            planned_mutations = [
                {
                    "area": "regime routing",
                    "intent": "either simplify the shared logic or split bull and bear rules",
                    "reason": "The analysis points to regime-specific failure modes.",
                }
            ]

        if family in planner_memory_snapshot.family_cooldowns:
            family = "replace_indicator"
            target_problem = (
                f"{target_problem.rstrip('.')} Similar family attempts have saturated recently."
            )
            expected_effect = "Try a different angle before repeating the same family."
            regime_policy = "preserve_current_regime_model"
            artifact_mode = "prefer_genome"
            planned_mutations = [
                {
                    "area": "indicator stack",
                    "intent": "replace one weak confirmation path instead of repeating a saturated family",
                    "reason": "Recent history suggests the prior family is not producing new information.",
                }
            ]

        if "rsi" in allowed_indicator_pool(knowledge_snippets) and family == "simplify_filters":
            planned_mutations.append(
                {
                    "area": "thresholds",
                    "intent": "widen RSI thresholds instead of adding another signal",
                    "reason": "The knowledge pack already discusses RSI behavior.",
                }
            )
        if any(item in allowed_indicator_pool(knowledge_snippets) for item in ("atr", "rolling_std")) and family in {"replace_indicator", "stabilize_turnover", "tighten_risk"}:
            planned_mutations.append(
                {
                    "area": "volatility filter",
                    "intent": "use a volatility filter only if it replaces a weaker clause",
                    "reason": "The knowledge pack includes volatility-oriented guidance.",
                }
            )

        carry_forward_lessons = (
            planner_memory_snapshot.carry_forward_lessons
            if planner_memory_snapshot.carry_forward_lessons
            else _extract_latest_lesson_statements(latest_lesson)
        )
        historical_risks = planner_memory_snapshot.repeated_failure_signals
        indicator_pool = allowed_indicator_pool(knowledge_snippets)
        context_signals = set(knowledge_context_signals(knowledge_snippets))
        context_signals.update(historical_risks)
        risk_signal_terms = {"turbulence", "covariance", "vix"}
        metadata_signal_terms = {
            "metadata",
            "sector",
            "industry",
            "exchange",
            "country",
            "universe",
            "market_cap",
        }

        if risk_signal_terms.intersection(context_signals) or any(
            token in analysis_text for token in risk_signal_terms
        ):
            planned_mutations.append(
                {
                    "area": "risk gating",
                    "intent": "tighten turbulence or covariance-aware gating before adding more exposure",
                    "reason": "Recent evidence points to stress-sensitive behavior instead of a missing entry trigger.",
                }
            )
        if metadata_signal_terms.intersection(context_signals) or any(
            token.replace("_", " ") in analysis_text or token in analysis_text
            for token in metadata_signal_terms
        ):
            planned_mutations.append(
                {
                    "area": "metadata robustness",
                    "intent": "prefer a change that stays stable across metadata slices instead of one market-specific fix",
                    "reason": "Recent evidence points to concentration in one sector, exchange, or market bucket.",
                }
            )
        change_budget = {
            "target_path": MUTABLE_STRATEGY_TARGET_PATH,
            "max_files": 1,
            "max_indicator_count": 4,
            "max_new_conditions": 2,
        }
        hypothesis = f"{family}: {planned_mutations[0]['intent']} because {target_problem.rstrip('.')}"
        plan_summary = (
            f"{target_problem} Focus on {planned_mutations[0]['area']} and keep edits inside one strategy file."
        )
        guardrails = _guardrails_to_watch(
            baseline_evaluation=baseline_evaluation,
            latest_metrics=latest_metrics,
            analysis_text=analysis_text,
            context_signals=context_signals,
        )
        return ResearchBrief(
            hypothesis=hypothesis,
            objective="Beat baseline score by at least 0.05 without triggering guardrail failures.",
            plan_summary=plan_summary,
            family=family,
            target_problem=target_problem,
            expected_effect=expected_effect,
            regime_policy=regime_policy,
            complexity_budget=change_budget,
            historical_risks=historical_risks,
            guardrails_to_watch=tuple(guardrails),
            carry_forward_lessons=tuple(carry_forward_lessons[:5]),
            planned_mutations=tuple(planned_mutations),
            artifact_mode=artifact_mode,
            allowed_indicator_pool=indicator_pool,
            knowledge_evidence=knowledge_evidence(knowledge_snippets),
            knowledge_source_ids=tuple(snippet.source_id for snippet in knowledge_snippets),
        )


def _guardrails_to_watch(
    *,
    baseline_evaluation: dict[str, Any],
    latest_metrics: dict[str, Any],
    analysis_text: str,
    context_signals: set[str],
) -> list[str]:
    guardrails: list[str] = [str(item) for item in latest_metrics.get("guardrail_failures", [])]
    if "exposure" in analysis_text:
        guardrails.append("Maintain non-zero exposure for every symbol and regime slice.")
    if "turnover" in analysis_text:
        guardrails.append("Keep mean out-of-sample turnover at or below 12.0.")
    if "drawdown" in analysis_text:
        guardrails.append("Keep the worst out-of-sample max drawdown at or below 0.35.")
    if {"turbulence", "covariance", "vix"}.intersection(context_signals) or any(
        token in analysis_text for token in ("turbulence", "covariance", "vix")
    ):
        guardrails.append(
            "Do not recover score by hiding behind turbulence-aware over-gating or zero exposure."
        )
    if {
        "metadata",
        "sector",
        "industry",
        "exchange",
        "country",
        "universe",
        "market_cap",
    }.intersection(context_signals) or any(
        token in analysis_text
        for token in ("metadata", "sector", "industry", "exchange", "country", "market", "universe")
    ):
        guardrails.append("Avoid solving the problem only inside one metadata slice or market bucket.")
    if not guardrails:
        if not bool(baseline_evaluation.get("guardrails_passed", True)):
            guardrails.append("Fix the baseline guardrail failure before chasing extra score.")
        else:
            guardrails.append("Preserve guardrail compliance while improving score.")
    return list(dict.fromkeys(guardrails))


def _extract_latest_lesson_statements(latest_lesson: Any) -> tuple[str, ...]:
    if latest_lesson is None:
        return ()
    lesson_output = getattr(latest_lesson, "lesson_output", {}) or {}
    statements: list[str] = []
    for lesson in lesson_output.get("lessons", []):
        if not isinstance(lesson, dict):
            continue
        statement = str(lesson.get("statement", "")).strip()
        if statement and statement not in statements:
            statements.append(statement)
        if len(statements) == 5:
            return tuple(statements)
    for action in lesson_output.get("next_actions", []):
        statement = str(action).strip()
        if statement and statement not in statements:
            statements.append(statement)
        if len(statements) == 5:
            break
    return tuple(statements)
