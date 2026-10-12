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
    dsr_methodology: str = "NORMAL_IID_TRIAL_PROXY"
    stability_methodology: str = "UNPURGED_FIXED_STRATEGY_GROUP_DIAGNOSTIC"
    pbo_methodology: str = "CSCV_LOG_RETURN_RANK_NO_REFIT"


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
    sample_returns: tuple[float, ...] | None = None,
    annualization_factor: float = 1.0,
) -> RobustnessReport:
    """Combine stress, temporal stability, DSR and cohort PBO evidence.

    The parameter_scores name is retained for compatibility. Current pipeline
    values are unpurged fixed-strategy grouped-return diagnostics, not evidence
    of complete purged/refitted CPCV paths.
    """

    if not all(
        math.isfinite(value)
        for value in (base_return, stressed_return, sharpe, *parameter_scores)
    ):
        raise ValueError("robustness financial inputs must be finite")
    if pbo is not None and (not math.isfinite(pbo) or not 0.0 <= pbo <= 1.0):
        raise ValueError("PBO must be finite and between zero and one")
    if not math.isfinite(annualization_factor) or annualization_factor <= 0:
        raise ValueError("annualization factor must be finite and positive")
    if sample_returns is not None:
        if len(sample_returns) != observations:
            raise ValueError("DSR sample observations must equal the return series length")
        if any(not math.isfinite(value) or value < -1 for value in sample_returns):
            raise ValueError("DSR requires finite returns not below -100%")
    if base_return == 0 or len(parameter_scores) < 2 or trials < 1 or observations < 2:
        return RobustnessReport(
            "INSUFFICIENT_EVIDENCE", 0.0, 0.0, None, pbo, 0.0,
            dsr_methodology="NOT_MEASURED",
            stability_methodology="NOT_MEASURED",
            pbo_methodology=(
                "CSCV_LOG_RETURN_RANK_NO_REFIT" if pbo is not None else "NOT_MEASURED"
            ),
        )

    # Cost resilience only has a meaningful positive ratio when the baseline
    # strategy made money. A negative return worsened by costs must not score
    # as perfectly resilient just because both numerator and denominator are negative.
    cost_sensitivity = clamp_unit(stressed_return / base_return) if base_return > 0 else 0.0
    mean = fmean(parameter_scores)
    stability = clamp_unit(1.0 / (1.0 + pstdev(parameter_scores) / max(abs(mean), 1e-12)))
    skewness, kurtosis = _return_moments(sample_returns)
    dsr = deflated_sharpe_ratio(
        sharpe,
        trials=trials,
        observations=observations,
        annualization_factor=annualization_factor,
        skewness=skewness,
        kurtosis=kurtosis,
    )
    return_quality = clamp_unit((base_return + 0.10) / 0.50)
    complexity_penalty = 1.0 / (1.0 + max(complexity, 0) * 0.02)
    pbo_modifier = 1.0 if pbo is None else 1.0 - 0.5 * pbo
    score = clamp_unit(
        (0.30 * stability + 0.20 * cost_sensitivity + 0.25 * dsr + 0.25 * return_quality)
        * pbo_modifier
    )
    return RobustnessReport(
        "OK",
        cost_sensitivity,
        stability,
        dsr,
        pbo,
        score * complexity_penalty,
        (
            "SAMPLE_MOMENTS_IID_TRIAL_PROXY"
            if sample_returns is not None and pstdev(sample_returns) > 0
            else "NORMAL_IID_TRIAL_PROXY"
        ),
    )


def _return_moments(returns: tuple[float, ...] | None) -> tuple[float, float]:
    """Observed skew and Pearson kurtosis, using population central moments.

    An unmeasured or constant series is treated as a *normal proxy*, not as
    proof of normally distributed returns.
    """
    if returns is None or len(returns) < 4:
        return 0.0, 3.0
    center = fmean(returns)
    scale = pstdev(returns)
    if scale <= 0:
        return 0.0, 3.0
    standardized = tuple((value - center) / scale for value in returns)
    return (
        fmean(value**3 for value in standardized),
        fmean(value**4 for value in standardized),
    )


def deflated_sharpe_ratio(
    sharpe: float,
    *,
    trials: int,
    observations: int,
    annualization_factor: float = 1.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Bailey/López de Prado DSR-style normal independent-trial *proxy*.

    The caller's Sharpe is annualized by annualization_factor; return count is
    measured in original bar frequency. Normal independent trial Sharpe
    variability is approximated as 1/sqrt(T-1) because true cross-trial
    variance/effective independent trials are not independently measured.
    This is not a production-qualified DSR or a statistical promotion gate.
    """
    if trials < 1 or observations < 2:
        raise ValueError("insufficient evidence for DSR")
    if not math.isfinite(annualization_factor) or annualization_factor <= 0:
        raise ValueError("annualization factor must be finite and positive")
    if not all(math.isfinite(value) for value in (sharpe, skewness, kurtosis)):
        raise ValueError("DSR parameters must be finite")
    if kurtosis < 1:
        raise ValueError("Pearson kurtosis cannot be below one")
    per_observation_sharpe = sharpe / math.sqrt(annualization_factor)
    if not math.isfinite(per_observation_sharpe):
        raise ValueError("DSR per-observation Sharpe must be finite")

    # Approximate E[max(SR)] for independent normal, null-mean Sharpe trials.
    expected_max = 0.0
    if trials > 1:
        euler = 0.5772156649015329
        dist = NormalDist()
        expected_max = (
            (1.0 - euler) * dist.inv_cdf(1.0 - 1.0 / trials)
            + euler * dist.inv_cdf(1.0 - 1.0 / (trials * math.e))
        ) / math.sqrt(observations - 1)
    denominator_variance = (
        1.0
        - skewness * per_observation_sharpe
        + ((kurtosis - 1.0) / 4.0) * per_observation_sharpe**2
    )
    if denominator_variance <= 0 or not math.isfinite(denominator_variance):
        raise ValueError("DSR moment-adjusted variance must be positive and finite")
    statistic = (
        (per_observation_sharpe - expected_max)
        * math.sqrt(observations - 1)
        / math.sqrt(denominator_variance)
    )
    return clamp_unit(NormalDist().cdf(statistic))


def group_holdout_return_scores(
    returns: tuple[float, ...],
    *,
    groups: int = 4,
    test_groups: int = 1,
) -> tuple[float, ...]:
    """Unpurged fixed-strategy holdout block returns (NOT fitted CPCV paths).

    These are descriptive grouped returns. No fold-specific model re-fitting,
    label-overlap purging, embargo, or combinatorial path reconstruction occurs.
    Do not present these scores as independently valid CPCV/OOS paths.
    """
    if len(returns) < groups:
        raise ValueError("insufficient return observations for grouped holdouts")
    if any(not math.isfinite(value) for value in returns):
        raise ValueError("group holdout returns must be finite")
    if any(value < -1.0 for value in returns):
        raise ValueError("group holdout returns cannot be below -100%")
    splits = cpcv_splits(tuple(range(len(returns))), groups=groups, test_groups=test_groups)
    return tuple(
        math.expm1(_log_return_score(returns, test_indices))
        for _train_indices, test_indices in splits
    )


def cpcv_return_scores(
    returns: tuple[float, ...],
    *,
    groups: int = 4,
    test_groups: int = 1,
) -> tuple[float, ...]:
    """Backward-compatible alias; see group_holdout_return_scores docstring."""
    return group_holdout_return_scores(returns, groups=groups, test_groups=test_groups)


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
    if groups < 2 or groups % 2 != 0 or test_groups * 2 != groups:
        raise ValueError("CSCV PBO requires symmetric train/test halves of even groups")
    widths = {len(values) for values in candidate_returns}
    if len(widths) != 1:
        raise ValueError("PBO candidate returns must be chronologically aligned")
    width = next(iter(widths))
    if width < groups:
        raise ValueError("insufficient return observations for PBO")
    if any(not math.isfinite(value) for values in candidate_returns for value in values):
        raise ValueError("PBO returns must be finite")
    if any(value < -1.0 for values in candidate_returns for value in values):
        raise ValueError("PBO returns cannot be below -100%")
    if all(values == candidate_returns[0] for values in candidate_returns[1:]):
        raise ValueError("PBO candidate cohort is indistinguishable")
    aligned = candidate_returns
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
