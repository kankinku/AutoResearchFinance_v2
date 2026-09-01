from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
    equity_curve: Sequence[float], risk: RiskConfig
) -> RiskEvaluation:
    if not equity_curve or any(value <= 0 for value in equity_curve):
        raise ValueError("equity curve must contain positive values")
    daily_losses = tuple(
        max(0.0, (previous - current) / previous * 100.0)
        for previous, current in zip(equity_curve, equity_curve[1:], strict=False)
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
