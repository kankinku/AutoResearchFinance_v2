from __future__ import annotations

import pytest

from evaluation.robustness import (
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
    )

    assert report.status == "OK"
    assert report.cost_sensitivity == pytest.approx(0.75)
    assert 0 < report.stability <= 1
    assert 0 < report.dsr <= 1
    assert 0 <= report.pbo <= 1
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
    with pytest.raises(ValueError, match="insufficient"):
        probability_backtest_overfitting(((0.8, 0.2),))
