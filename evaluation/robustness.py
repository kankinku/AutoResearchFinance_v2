from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist, fmean, pstdev


@dataclass(frozen=True)
class RobustnessReport:
    status: str
    cost_sensitivity: float
    stability: float
    dsr: float | None
    pbo: float | None
    robust_score: float


def robust_statistics(
    *,
    base_return: float,
    stressed_return: float,
    parameter_scores: tuple[float, ...],
    sharpe: float,
    trials: int,
    observations: int,
    complexity: int,
) -> RobustnessReport:
    if base_return == 0 or len(parameter_scores) < 3 or trials < 1 or observations < 2:
        return RobustnessReport("INSUFFICIENT_EVIDENCE", 0.0, 0.0, None, None, 0.0)
    cost_sensitivity = _clamp(stressed_return / base_return)
    mean = fmean(parameter_scores)
    stability = _clamp(1.0 / (1.0 + pstdev(parameter_scores) / max(abs(mean), 1e-12)))
    dsr = deflated_sharpe_ratio(sharpe, trials=trials, observations=observations)
    paired_scores = tuple(zip(parameter_scores, parameter_scores[1:], strict=False))
    pbo = probability_backtest_overfitting(paired_scores)
    complexity_penalty = 1.0 / (1.0 + max(complexity, 0) * 0.02)
    score = _clamp((0.4 * stability + 0.3 * cost_sensitivity + 0.3 * dsr) * (1 - 0.5 * pbo))
    return RobustnessReport("OK", cost_sensitivity, stability, dsr, pbo, score * complexity_penalty)


def deflated_sharpe_ratio(sharpe: float, *, trials: int, observations: int) -> float:
    if trials < 1 or observations < 2:
        raise ValueError("insufficient evidence for DSR")
    expected_max = math.sqrt(2.0 * math.log(max(trials, 1)))
    standard_error = math.sqrt(max(1.0 + (sharpe * sharpe) / 2.0, 1e-12) / observations)
    return _clamp(NormalDist().cdf((sharpe - expected_max) / standard_error))


def probability_backtest_overfitting(scores: tuple[tuple[float, float], ...]) -> float:
    if len(scores) < 2:
        raise ValueError("insufficient evidence for PBO")
    underperforming = sum(out_sample < in_sample for in_sample, out_sample in scores)
    return underperforming / len(scores)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
