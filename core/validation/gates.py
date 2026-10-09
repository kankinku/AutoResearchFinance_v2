from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


class MetricsView(Protocol):
    """Minimal core contract independent of evaluation post-processing."""

    trade_count: int
    total_return: float


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: tuple[str, ...]


def hard_gate(metrics: MetricsView, *, min_trade_count: int, min_return: float) -> GateResult:
    reasons: list[str] = []
    if metrics.trade_count < min_trade_count:
        reasons.append("trade_count")
    if metrics.total_return < min_return:
        reasons.append("total_return")
    if not math.isfinite(metrics.total_return):
        reasons.append("non_finite_return")
    return GateResult(not reasons, tuple(reasons))
