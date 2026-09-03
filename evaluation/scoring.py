from __future__ import annotations

from dataclasses import dataclass

from evaluation.metrics import Metrics
from evaluation.utils import clamp_unit


@dataclass(frozen=True)
class RobustnessInputs:
    stability: float
    cost_sensitivity: float
    complexity: int


def robust_score(metrics: Metrics, robustness: RobustnessInputs) -> float:
    sharpe_component = clamp_unit(((metrics.sharpe or 0.0) + 1.0) / 4.0)
    return_component = clamp_unit((metrics.cagr + 0.1) / 0.5)
    drawdown_component = 1.0 - clamp_unit(metrics.max_drawdown)
    complexity_penalty = 1.0 / (1.0 + max(robustness.complexity, 0) * 0.02)
    raw = (
        0.50 * return_component
        + 0.20 * sharpe_component
        + 0.15 * drawdown_component
        + 0.15 * clamp_unit(robustness.stability)
    )
    cost_modifier = 0.75 + 0.25 * clamp_unit(robustness.cost_sensitivity)
    complexity_modifier = 0.85 + 0.15 * complexity_penalty
    return clamp_unit(raw * cost_modifier * complexity_modifier)
