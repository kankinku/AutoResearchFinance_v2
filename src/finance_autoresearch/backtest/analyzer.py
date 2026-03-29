from __future__ import annotations

from typing import Any

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer


def analyze_backtest_results(
    backtest_results: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    localizer: OutputLocalizer | None = None,
) -> dict[str, Any]:
    resolved_localizer = localizer or DEFAULT_LOCALIZER
    aggregate = evaluation["metrics"]["aggregate"]
    strengths: list[str] = []
    weaknesses: list[str] = []
    coverage_gaps: list[str] = []
    regime_observations: list[str] = []
    next_hypothesis_hints: list[str] = []

    score = float(evaluation["score"])
    if score > 0.0:
        strengths.append(resolved_localizer.log("analyzer.score_positive", score=score))
    else:
        weaknesses.append(resolved_localizer.log("analyzer.score_weak", score=score))

    if evaluation["guardrails_passed"]:
        strengths.append(resolved_localizer.log("analyzer.guardrails_passed"))
    else:
        weaknesses.extend(evaluation["guardrail_failures"])
        coverage_gaps.extend(evaluation["guardrail_failures"])

    if aggregate["mean_out_of_sample_total_return"] > 0.0:
        strengths.append(resolved_localizer.log("analyzer.return_positive"))
    else:
        weaknesses.append(resolved_localizer.log("analyzer.return_not_positive"))

    if aggregate["worst_out_of_sample_max_drawdown"] > 0.25:
        regime_observations.append(resolved_localizer.log("analyzer.drawdown_elevated"))
        next_hypothesis_hints.append(resolved_localizer.log("analyzer.tighten_exits"))
    else:
        regime_observations.append(resolved_localizer.log("analyzer.drawdown_contained"))

    if aggregate["mean_out_of_sample_turnover"] > 10.0:
        coverage_gaps.append(resolved_localizer.log("analyzer.turnover_high"))
        next_hypothesis_hints.append(resolved_localizer.log("analyzer.reduce_churn"))
    else:
        strengths.append(resolved_localizer.log("analyzer.turnover_below_cap"))

    if not next_hypothesis_hints:
        next_hypothesis_hints.append(resolved_localizer.log("analyzer.default_hint"))
    if not coverage_gaps:
        coverage_gaps.append(resolved_localizer.log("analyzer.default_coverage_gap"))

    guardrail_status_key = (
        "analyzer.guardrails_status_passed"
        if evaluation["guardrails_passed"]
        else "analyzer.guardrails_status_failed"
    )
    summary = resolved_localizer.log(
        "analyzer.summary",
        score=score,
        guardrail_status=resolved_localizer.log(guardrail_status_key),
        mean_return=aggregate["mean_out_of_sample_total_return"],
    )
    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "coverage_gaps": coverage_gaps,
        "regime_observations": regime_observations,
        "next_hypothesis_hints": next_hypothesis_hints,
        "summary": summary,
    }
