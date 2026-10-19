"""Cash-denominated stop/target conversion for research-only position planning.

Based on the calculation concept in adolgov's Pine v4 example,
"Stop loss and Take Profit in $$ example" (© adolgov, MPL-2.0).
This is not an order execution engine; pending fills and gap risk need
separate broker-emulator validation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CashRiskLevels:
    stop_price: float
    target_price: float
    stop_ticks: int
    target_ticks: int
    stop_cash: float
    target_cash: float


def cash_risk_levels(
    *,
    avg_entry_price: float,
    signed_quantity: float,
    point_value: float,
    tick_size: float,
    stop_budget: float,
    target_budget: float,
) -> CashRiskLevels:
    """Compute executable whole-tick thresholds for a signed position.

    Round *down* to ticks, so the modeled cash amounts do not exceed
    budgets before commissions, slippage, and opening gaps. Pine's
    strategy.exit(..., profit=..., loss=...) uses tick distances; this
    primitive deliberately adds explicit rounding for risk budgeting.
    """
    values = (avg_entry_price, signed_quantity, point_value, tick_size, stop_budget, target_budget)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("all inputs must be finite")
    if avg_entry_price <= 0 or signed_quantity == 0 or point_value <= 0 or tick_size <= 0:
        raise ValueError("price, quantity magnitude, point value and tick size must be positive")
    if stop_budget <= 0 or target_budget <= 0:
        raise ValueError("cash budgets must be positive")
    cash_per_tick = abs(signed_quantity) * point_value * tick_size
    stop_ticks = math.floor(stop_budget / cash_per_tick + 1e-12)
    target_ticks = math.floor(target_budget / cash_per_tick + 1e-12)
    if min(stop_ticks, target_ticks) < 1:
        raise ValueError("cash budget smaller than one executable tick")
    side = 1 if signed_quantity > 0 else -1
    return CashRiskLevels(
        stop_price=avg_entry_price - side * stop_ticks * tick_size,
        target_price=avg_entry_price + side * target_ticks * tick_size,
        stop_ticks=stop_ticks,
        target_ticks=target_ticks,
        stop_cash=stop_ticks * cash_per_tick,
        target_cash=target_ticks * cash_per_tick,
    )
