from __future__ import annotations

from evaluation.metrics import calculate_metrics
from evaluation.scoring import RobustnessInputs, robust_score


def test_robust_score_rewards_stability_and_penalizes_complexity() -> None:
    metrics = calculate_metrics((100.0, 105.0, 110.0), (5.0, 5.0), periods_per_year=2)
    stable_simple = robust_score(metrics, RobustnessInputs(1.0, 1.0, complexity=2))
    unstable_complex = robust_score(metrics, RobustnessInputs(0.5, 0.5, complexity=20))

    assert stable_simple > unstable_complex
    assert 0.0 <= stable_simple <= 1.0


def test_robust_score_prioritizes_absolute_profitability() -> None:
    profitable = calculate_metrics((100.0, 120.0, 140.0), (20.0,), periods_per_year=2)
    modest = calculate_metrics((100.0, 102.0, 104.0), (4.0,), periods_per_year=2)

    assert robust_score(profitable, RobustnessInputs(0.5, 0.5, complexity=2)) > robust_score(
        modest, RobustnessInputs(1.0, 1.0, complexity=0)
    )
