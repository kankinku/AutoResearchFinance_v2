from __future__ import annotations

import pytest

from evaluation.robustness import (
    cpcv_return_scores,
    probability_backtest_overfitting,
    robust_statistics,
)


def test_robust_statistics_combines_stress_and_parameter_stability() -> None:
    report = robust_statistics(
        base_return=0.20,
        stressed_return=0.15,
        parameter_scores=(0.78, 0.80, 0.76),
        sharpe=1.5,
        trials=20,
        observations=100,
        complexity=5,
        pbo=0.25,
    )

    assert report.status == "OK"
    assert report.cost_sensitivity == pytest.approx(0.75)
    assert 0 < report.stability <= 1
    assert 0 < report.dsr <= 1
    assert report.pbo == pytest.approx(0.25)
    assert 0 < report.robust_score <= 1


def test_robust_statistics_does_not_fabricate_insufficient_dsr_or_pbo() -> None:
    report = robust_statistics(
        base_return=0.20,
        stressed_return=0.15,
        parameter_scores=(0.78,),
        sharpe=1.5,
        trials=0,
        observations=1,
        complexity=5,
    )

    assert report.status == "INSUFFICIENT_EVIDENCE"
    assert report.dsr is None
    assert report.pbo is None
    with pytest.raises(ValueError, match="candidate cohort"):
        probability_backtest_overfitting(((0.01, 0.02, 0.03, 0.04),))


def test_pbo_uses_candidate_cohort_and_cscv_splits() -> None:
    pbo = probability_backtest_overfitting(
        (
            (0.10, 0.10, 0.10, 0.10, -0.10, -0.10, -0.10, -0.10),
            (-0.02, -0.02, -0.02, -0.02, 0.03, 0.03, 0.03, 0.03),
            (0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01),
        )
    )

    assert pbo == pytest.approx(1 / 3)


def test_robust_score_is_penalized_by_pbo() -> None:
    low_pbo = robust_statistics(
        base_return=0.20,
        stressed_return=0.15,
        parameter_scores=(0.12, 0.10, 0.11),
        sharpe=1.5,
        trials=20,
        observations=100,
        complexity=5,
        pbo=0.0,
    )
    high_pbo = robust_statistics(
        base_return=0.20,
        stressed_return=0.15,
        parameter_scores=(0.12, 0.10, 0.11),
        sharpe=1.5,
        trials=20,
        observations=100,
        complexity=5,
        pbo=1.0,
    )

    assert high_pbo.robust_score < low_pbo.robust_score


def test_cpcv_return_scores_use_held_out_return_paths() -> None:
    scores = cpcv_return_scores((0.10, -0.05, 0.02, 0.03, 0.01, -0.02, 0.04, 0.05))

    assert len(scores) == 4
    assert len(set(scores)) > 1
