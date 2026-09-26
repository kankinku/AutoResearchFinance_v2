from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from strategy_ir.schema import RiskConfig


@dataclass(frozen=True)
class RiskEvaluation:
    risk_appetite: float | None
    loss_tolerance_pct: float | None
    daily_loss_limit_pct: float | None
    daily_loss_action: str
    max_daily_loss_pct: float
    daily_loss_breaches: int
    compliant: bool

    @property
    def action(self) -> str:
        return self.daily_loss_action


def evaluate_risk_policy(
    equity_curve: Sequence[float],
    risk: RiskConfig,
    *,
    timestamps: Sequence[datetime] | None = None,
) -> RiskEvaluation:
    if not equity_curve or any(value <= 0 for value in equity_curve):
        raise ValueError("equity curve must contain positive values")
    if timestamps is not None and len(timestamps) != len(equity_curve):
        raise ValueError("timestamps must match equity curve length")

    daily_losses = (
        _calendar_daily_losses(equity_curve, timestamps)
        if timestamps is not None
        else _bar_losses(equity_curve)
    )
    maximum = max(daily_losses, default=0.0)
    limit = risk.daily_loss_limit_pct
    breaches = sum(loss > limit for loss in daily_losses) if limit is not None else 0
    return RiskEvaluation(
        risk.risk_appetite,
        risk.loss_tolerance_pct,
        limit,
        risk.daily_loss_action,
        maximum,
        breaches,
        breaches == 0,
    )


def _bar_losses(equity_curve: Sequence[float]) -> tuple[float, ...]:
    """Legacy fallback for callers that do not yet supply timestamps."""

    return tuple(
        max(0.0, (previous - current) / previous * 100.0)
        for previous, current in zip(equity_curve, equity_curve[1:], strict=False)
    )


def _calendar_daily_losses(
    equity_curve: Sequence[float],
    timestamps: Sequence[datetime],
) -> tuple[float, ...]:
    if not timestamps:
        return ()

    losses: list[float] = []
    previous_close: float | None = None
    start = 0
    while start < len(timestamps):
        day = timestamps[start].date()
        end = start + 1
        while end < len(timestamps) and timestamps[end].date() == day:
            end += 1
        values = tuple(float(value) for value in equity_curve[start:end])
        day_start = previous_close if previous_close is not None else values[0]
        minimum = min((day_start, *values))
        losses.append(max(0.0, (day_start - minimum) / day_start * 100.0))
        previous_close = values[-1]
        start = end
    return tuple(losses)
