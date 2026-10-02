from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist, fmean, pstdev

from core.validation.cpcv import cpcv_splits
from core.validation.cscv import cscv_splits
from evaluation.utils import clamp_unit


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
    pbo: float | None = None,
) -> RobustnessReport:
    """Combine stress, temporal stability, DSR and cohort PBO evidence.

    The parameter_scores name is retained for compatibility, but callers should
    pass independent temporal-validation scores instead of fast/full/stress
    summary returns.
    """

    if base_return == 0 or len(parameter_scores) < 2 or trials < 1 or observations < 2:
        return RobustnessReport("INSUFFICIENT_EVIDENCE", 0.0, 0.0, None, pbo, 0.0)
    if pbo is not None and not 0.0 <= pbo <= 1.0:
        raise ValueError("PBO must be between zero and one")

    cost_sensitivity = clamp_unit(stressed_return / base_return)
    mean = fmean(parameter_scores)
    stability = clamp_unit(1.0 / (1.0 + pstdev(parameter_scores) / max(abs(mean), 1e-12)))
    dsr = deflated_sharpe_ratio(sharpe, trials=trials, observations=observations)
    return_quality = clamp_unit((base_return + 0.10) / 0.50)
    complexity_penalty = 1.0 / (1.0 + max(complexity, 0) * 0.02)
    pbo_modifier = 1.0 if pbo is None else 1.0 - 0.5 * pbo
    score = clamp_unit(
        (
            0.30 * stability
            + 0.20 * cost_sensitivity
            + 0.25 * dsr
            + 0.25 * return_quality
        )
        * pbo_modifier
    )
    return RobustnessReport(
        "OK",
        cost_sensitivity,
        stability,
        dsr,
        pbo,
        score * complexity_penalty,
    )


def deflated_sharpe_ratio(sharpe: float, *, trials: int, observations: int) -> float:
    if trials < 1 or observations < 2:
        raise ValueError("insufficient evidence for DSR")
    expected_max = math.sqrt(2.0 * math.log(max(trials, 1)))
    standard_error = math.sqrt(max(1.0 + (sharpe * sharpe) / 2.0, 1e-12) / observations)
    return clamp_unit(NormalDist().cdf((sharpe - expected_max) / standard_error))


def cpcv_return_scores(
    returns: tuple[float, ...],
    *,
    groups: int = 4,
    test_groups: int = 1,
) -> tuple[float, ...]:
    """Return held-out compounded returns across CPCV paths."""

    if len(returns) < groups:
        raise ValueError("insufficient return observations for CPCV")
    splits = cpcv_splits(tuple(range(len(returns))), groups=groups, test_groups=test_groups)
    return tuple(
        math.expm1(_log_return_score(returns, test_indices))
        for _train_indices, test_indices in splits
    )


def probability_backtest_overfitting(
    candidate_returns: tuple[tuple[float, ...], ...],
    *,
    groups: int = 4,
    test_groups: int = 2,
) -> float:
    """Estimate cohort PBO with CSCV splits.

    For each split, the candidate with the highest in-sample log-return score is
    selected. The split is counted as overfit when that selected candidate lands
    in the bottom half of the cohort out of sample.
    """

    if len(candidate_returns) < 2:
        raise ValueError("insufficient candidate cohort for PBO")
    width = min((len(values) for values in candidate_returns), default=0)
    if width < groups:
        raise ValueError("insufficient return observations for PBO")
    aligned = tuple(tuple(values[:width]) for values in candidate_returns)
    splits = cscv_splits(tuple(range(width)), groups=groups, test_groups=test_groups)
    if not splits:
        raise ValueError("insufficient CSCV splits for PBO")

    overfit = 0
    for train_indices, test_indices in splits:
        train_scores = tuple(_log_return_score(values, train_indices) for values in aligned)
        test_scores = tuple(_log_return_score(values, test_indices) for values in aligned)
        selected = max(range(len(aligned)), key=lambda index: (train_scores[index], -index))
        selected_oos = test_scores[selected]
        below = sum(score < selected_oos for score in test_scores)
        tied = sum(score == selected_oos for score in test_scores)
        percentile = (below + 0.5 * tied) / len(test_scores)
        if percentile <= 0.5:
            overfit += 1
    return overfit / len(splits)


def _log_return_score(values: tuple[float, ...], indices: tuple[int, ...]) -> float:
    total = 0.0
    for index in indices:
        value = values[index]
        if value <= -1.0:
            return float("-inf")
        total += math.log1p(value)
    return total
