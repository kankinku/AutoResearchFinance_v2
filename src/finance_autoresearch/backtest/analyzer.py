from __future__ import annotations

from typing import Any


def analyze_backtest_results(
    backtest_results: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    aggregate = evaluation["metrics"]["aggregate"]
    strengths: list[str] = []
    weaknesses: list[str] = []
    coverage_gaps: list[str] = []
    regime_observations: list[str] = []
    next_hypothesis_hints: list[str] = []

    score = float(evaluation["score"])
    if score > 0.0:
        strengths.append(f"Median out-of-sample Sharpe remained positive at {score:.2f}.")
    else:
        weaknesses.append(f"Median out-of-sample Sharpe was weak at {score:.2f}.")

    if evaluation["guardrails_passed"]:
        strengths.append("All fixed guardrails passed across the six combinations.")
    else:
        weaknesses.extend(evaluation["guardrail_failures"])
        coverage_gaps.extend(evaluation["guardrail_failures"])

    if aggregate["mean_out_of_sample_total_return"] > 0.0:
        strengths.append("Average out-of-sample total return stayed positive.")
    else:
        weaknesses.append("Average out-of-sample total return was not positive.")

    if aggregate["worst_out_of_sample_max_drawdown"] > 0.25:
        regime_observations.append("Worst-case drawdown remains materially elevated in at least one combination.")
        next_hypothesis_hints.append("Tighten exits or reduce exposure in the weakest out-of-sample regime.")
    else:
        regime_observations.append("Worst-case drawdown remained contained relative to the fixed 0.35 cap.")

    if aggregate["mean_out_of_sample_turnover"] > 10.0:
        coverage_gaps.append("Turnover is close to the fixed cap and may need smoother entry filters.")
        next_hypothesis_hints.append("Reduce churn with slower confirmation or regime-specific gating.")
    else:
        strengths.append("Mean out-of-sample turnover stayed comfortably below the fixed cap.")

    if not next_hypothesis_hints:
        next_hypothesis_hints.append("Stress the weaker symbol/timeframe pairs with more selective exits.")
    if not coverage_gaps:
        coverage_gaps.append("Investigate whether regime coverage is balanced across all symbols.")

    summary = (
        f"Score {score:.2f}; "
        f"{'guardrails passed' if evaluation['guardrails_passed'] else 'guardrails failed'}; "
        f"mean OOS return {aggregate['mean_out_of_sample_total_return']:.2%}."
    )
    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "coverage_gaps": coverage_gaps,
        "regime_observations": regime_observations,
        "next_hypothesis_hints": next_hypothesis_hints,
        "summary": summary,
    }
