from __future__ import annotations

from dataclasses import dataclass

from evaluation.metrics import Metrics


@dataclass(frozen=True)
class RobustnessInputs:
    stability: float
    cost_sensitivity: float
    complexity: int


def robust_score(metrics: Metrics, robustness: RobustnessInputs) -> float:
    sharpe_component = _clamp(((metrics.sharpe or 0.0) + 1.0) / 4.0)
    return_component = _clamp((metrics.cagr + 0.1) / 0.5)
    drawdown_component = 1.0 - _clamp(metrics.max_drawdown)
    complexity_penalty = 1.0 / (1.0 + max(robustness.complexity, 0) * 0.02)
    raw = (
        0.35 * sharpe_component
        + 0.30 * return_component
        + 0.20 * drawdown_component
        + 0.15 * _clamp(robustness.stability)
    )
    return _clamp(raw * _clamp(robustness.cost_sensitivity) * complexity_penalty)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
