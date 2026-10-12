"""Independent, small arithmetic references for financial statistics.

The DSR expectation is the *normal independent-trial proxy*, not verified
effective-trial counts or an inference about market validity.
"""

from __future__ import annotations

from itertools import combinations
from math import exp, isfinite, log, sqrt
from statistics import NormalDist

import pytest

from evaluation.robustness import (
    cpcv_return_scores,
    deflated_sharpe_ratio,
    group_holdout_return_scores,
    probability_backtest_overfitting,
)


def _reference_iid_dsr(
    sharpe: float, *, trials: int, observations: int, annualization_factor: float
) -> float:
    daily_sharpe = sharpe / sqrt(annualization_factor)
    null_sd = 1.0 / sqrt(observations - 1)
    if trials == 1:
        expected_max = 0.0
    else:
        euler = 0.5772156649015329
        expected_max = null_sd * (
            (1.0 - euler) * NormalDist().inv_cdf(1.0 - 1.0 / trials)
            + euler * NormalDist().inv_cdf(1.0 - 1.0 / (trials * exp(1.0)))
        )
    sample_sd = sqrt((1.0 + daily_sharpe * daily_sharpe / 2.0) / (observations - 1))
    return NormalDist().cdf((daily_sharpe - expected_max) / sample_sd)


def test_dsr_matches_independent_normal_null_reference() -> None:
    got = deflated_sharpe_ratio(1.5, trials=20, observations=252, annualization_factor=252.0)
    assert got == pytest.approx(
        _reference_iid_dsr(1.5, trials=20, observations=252, annualization_factor=252.0),
        abs=1e-12,
    )


def test_dsr_annualization_is_unit_invariant() -> None:
    yearly = deflated_sharpe_ratio(1.8, trials=12, observations=500, annualization_factor=252.0)
    daily = deflated_sharpe_ratio(
        1.8 / sqrt(252.0), trials=12, observations=500, annualization_factor=1.0
    )
    assert yearly == pytest.approx(daily, abs=1e-12)


def test_dsr_one_trial_zero_sharpe_has_normal_null_probability() -> None:
    assert deflated_sharpe_ratio(0.0, trials=1, observations=50) == pytest.approx(0.5)


def test_dsr_more_trials_requires_stronger_sharpe() -> None:
    low = deflated_sharpe_ratio(1.5, trials=2, observations=252, annualization_factor=252)
    high = deflated_sharpe_ratio(1.5, trials=200, observations=252, annualization_factor=252)
    assert 0 < high < low < 1


@pytest.mark.parametrize("wrong", [float("nan"), float("inf"), -10.0, 0.0])
def test_dsr_invalid_annualization_rejected(wrong: float) -> None:
    with pytest.raises(ValueError, match="annualization"):
        deflated_sharpe_ratio(1.0, trials=10, observations=100, annualization_factor=wrong)


def test_pbo_is_cscv_and_requires_equal_in_sample_and_out_of_sample_groups() -> None:
    cohort = (
        (0.10, 0.09, 0.08, -0.09, -0.08, -0.10, 0.01, 0.02),
        (-0.04, -0.02, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06),
    )
    for groups, test_groups in ((3, 1), (4, 1), (4, 3), (5, 2)):
        with pytest.raises(ValueError, match="symmetric|half|even"):
            probability_backtest_overfitting(cohort, groups=groups, test_groups=test_groups)
    assert 0 <= probability_backtest_overfitting(cohort, groups=4, test_groups=2) <= 1


def test_pbo_matches_independent_bruteforce_enumeration_for_two_models() -> None:
    cohort = (
        (0.20, 0.20, -0.20, -0.20, 0.12, 0.12, -0.08, -0.08),
        (-0.05, -0.05, 0.12, 0.12, -0.08, -0.08, 0.14, 0.14),
    )
    negative_rank = 0
    for train_groups in combinations(range(4), 2):
        train_indices = [2 * group + offset for group in train_groups for offset in range(2)]
        test_indices = [i for i in range(8) if i not in train_indices]
        train_scores = [sum(log(1 + returns[i]) for i in train_indices) for returns in cohort]
        test_scores = [sum(log(1 + returns[i]) for i in test_indices) for returns in cohort]
        winner = max(range(2), key=lambda i: (train_scores[i], -i))
        percentile = (
            sum(score < test_scores[winner] for score in test_scores)
            + 0.5 * sum(score == test_scores[winner] for score in test_scores)
        ) / 2
        negative_rank += percentile <= 0.5
    expected = negative_rank / 6
    got = probability_backtest_overfitting(cohort)
    assert got == pytest.approx(expected)


def test_grouped_returns_are_split_diagnostics_not_complete_cpcv_paths() -> None:
    returns = (0.10, 0.01, 0.04, -0.02, 0.02, 0.03, 0.05, -0.03)
    expected = tuple((1 + returns[2 * i]) * (1 + returns[2 * i + 1]) - 1 for i in range(4))
    assert group_holdout_return_scores(returns) == pytest.approx(expected)
    assert cpcv_return_scores(returns) == pytest.approx(expected)
    assert all(isfinite(item) for item in expected)


def test_pipeline_evidence_identifies_unverified_statistical_methods() -> None:
    from orchestration.evidence import candidate_evidence
    from tests.orchestration.test_train_only_selection import data, evaluate

    result = evaluate(data())
    assert result.funnel
    row = candidate_evidence(result.funnel[0])
    assert row["dsr_methodology"] in {
        "SAMPLE_MOMENTS_IID_TRIAL_PROXY", "NORMAL_IID_TRIAL_PROXY"
    }
    assert row["stability_methodology"] == "UNPURGED_FIXED_STRATEGY_GROUP_DIAGNOSTIC"
    assert row["pbo_methodology"] in {
        "CSCV_LOG_RETURN_RANK_NO_REFIT", "NOT_MEASURED"
    }
    assert row["cpcv_full_paths"] == "NOT_MEASURED"


def test_return_history_moments_are_measured_for_dsr_and_invariant_to_scale() -> None:
    from evaluation.robustness import robust_statistics

    returns = (0.02, -0.05, 0.01, 0.03, -0.02, 0.04, 0.01, 0.02)
    base = dict(
        base_return=0.05, stressed_return=0.03,
        parameter_scores=(0.01, 0.02, 0.0, 0.03),
        trials=12, observations=len(returns), complexity=2,
        sample_returns=returns,
    )
    first = robust_statistics(
        sharpe=1.2, annualization_factor=252, **base
    )
    second = robust_statistics(
        sharpe=1.2 / sqrt(252), annualization_factor=1, **base
    )
    assert first.dsr_methodology == "SAMPLE_MOMENTS_IID_TRIAL_PROXY"
    assert first.dsr == pytest.approx(second.dsr, abs=1e-12)
    assert first.stability_methodology == "UNPURGED_FIXED_STRATEGY_GROUP_DIAGNOSTIC"
