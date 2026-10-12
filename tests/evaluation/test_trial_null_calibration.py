"""Closed-form, reproducible anchors for Gaussian max-score null calibration."""
from __future__ import annotations

from math import pi, sqrt

import pytest

from evaluation.trial_dependence import estimate_cohort_dependence
from evaluation.trial_null_calibration import (
    calibrate_cohort_gaussian_null,
    iid_equivalent_k,
    iid_gaussian_max_expectation,
)


def test_iid_reference_matches_two_normal_analytic_expectation() -> None:
    # E[max(Z1,Z2)] = 1/sqrt(pi) for independent N(0,1).
    assert iid_gaussian_max_expectation(1) == 0.0
    expected = 1 / sqrt(pi)
    assert iid_gaussian_max_expectation(2) == pytest.approx(expected, abs=0.00002)
    assert iid_equivalent_k(expected) == pytest.approx(2, abs=0.0001)


def test_null_simulation_reproduces_independent_two_score_reference() -> None:
    import numpy as np

    correlation = np.eye(2)
    mean, interval, k, k_interval = calibrate_cohort_gaussian_null(correlation)
    assert mean == pytest.approx(1 / sqrt(pi), abs=0.05)
    assert interval[0] < mean < interval[1]
    assert k == pytest.approx(2, abs=0.30)
    assert k_interval[0] <= k <= k_interval[1]
    assert calibrate_cohort_gaussian_null(correlation) == (
        mean, interval, k, k_interval
    )


def test_perfectly_anti_correlated_strategies_are_not_iid_trial_one() -> None:
    import numpy as np

    same = np.array([[1.0, 1.0], [1.0, 1.0]])
    opposite = np.array([[1.0, -1.0], [-1.0, 1.0]])
    positive = calibrate_cohort_gaussian_null(same)
    negative = calibrate_cohort_gaussian_null(opposite)
    assert positive[2] == pytest.approx(1.0, abs=0.1)
    # E[max(Z,-Z)]=sqrt(2/pi) > E[max(Z1,Z2)].
    assert negative[0] == pytest.approx(sqrt(2 / pi), abs=0.05)
    assert negative[2] > 2.0
    assert negative[2] > positive[2]


def test_empirical_training_diagnostic_contains_conditional_monte_carlo_error() -> None:
    values = tuple(v / 100 for v in (3, 2, 1, -1) * 12)
    report = estimate_cohort_dependence((values, values))
    assert report.status == "ESTIMATED_TRAIN_ONLY_COHORT"
    assert report.effective_rank == pytest.approx(1)
    assert report.null_model == "GAUSSIAN_SHARPE_Z_EMPIRICAL_TRAIN_CORRELATION"
    assert report.null_monte_carlo_draws == 4096
    assert report.iid_equivalent_trials_estimate is not None
    assert report.null_max_sharpe_z_ci95 is not None
    assert report.iid_equivalent_trials_ci95 is not None
    assert report.dsr_calibrated is False


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 0.5])
def test_invalid_iid_reference_k_denied(invalid: float) -> None:
    with pytest.raises(ValueError):
        iid_gaussian_max_expectation(invalid)
