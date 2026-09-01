from __future__ import annotations

from evaluation.metrics import calculate_metrics
from evaluation.scoring import RobustnessInputs, robust_score


def test_robust_score_rewards_stability_and_penalizes_complexity() -> None:
    metrics = calculate_metrics((100.0, 105.0, 110.0), (5.0, 5.0), periods_per_year=2)
    stable_simple = robust_score(metrics, RobustnessInputs(1.0, 1.0, complexity=2))
    unstable_complex = robust_score(metrics, RobustnessInputs(0.5, 0.5, complexity=20))

    assert stable_simple > unstable_complex
    assert 0.0 <= stable_simple <= 1.0
