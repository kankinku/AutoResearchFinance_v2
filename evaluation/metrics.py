from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean, pstdev


@dataclass(frozen=True)
class Metrics:
    total_return: float
    cagr: float
    sharpe: float | None
    sortino: float | None
    max_drawdown: float
    calmar: float | None
    win_rate: float | None
    profit_factor: float | None
    trade_count: int
    turnover: float
    exposure: float


def calculate_metrics(
    equity_curve: Sequence[float],
    trade_pnls: Sequence[float],
    *,
    periods_per_year: float,
    turnover: float = 0.0,
    exposure: float = 0.0,
) -> Metrics:
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    if not equity_curve or any(value <= 0 for value in equity_curve):
        raise ValueError("equity curve must contain positive values")
    initial, final = equity_curve[0], equity_curve[-1]
    total_return = final / initial - 1.0
    years = max((len(equity_curve) - 1) / periods_per_year, 0.0)
    cagr = (final / initial) ** (1.0 / years) - 1.0 if years else 0.0
    returns = tuple(current / previous - 1.0 for previous, current in _pairs(equity_curve))
    sharpe = (
        _ratio(fmean(returns), pstdev(returns), periods_per_year**0.5)
        if len(returns) >= 2
        else None
    )
    downside = tuple(min(value, 0.0) for value in returns)
    downside_deviation = math.sqrt(fmean(value * value for value in downside)) if downside else 0.0
    sortino = _ratio(fmean(returns), downside_deviation, periods_per_year**0.5) if returns else None
    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)
    calmar = cagr / max_drawdown if max_drawdown else None
    wins = sum(value > 0 for value in trade_pnls)
    losses = sum(value < 0 for value in trade_pnls)
    gross_profit = sum(value for value in trade_pnls if value > 0)
    gross_loss = abs(sum(value for value in trade_pnls if value < 0))
    return Metrics(
        total_return,
        cagr,
        sharpe,
        sortino,
        max_drawdown,
        calmar,
        wins / (wins + losses) if wins + losses else None,
        gross_profit / gross_loss if gross_loss else None,
        len(trade_pnls),
        turnover,
        exposure,
    )


def _pairs(values: Sequence[float]) -> zip[tuple[float, float]]:
    return zip(values, values[1:], strict=False)


def _ratio(mean: float, deviation: float, annualization: float) -> float | None:
    return mean / deviation * annualization if deviation else None
