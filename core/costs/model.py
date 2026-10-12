from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from core.costs.slippage import SlippageModel


@dataclass(frozen=True)
class TradeCost:
    version: str
    notional: float
    commission: float
    spread: float
    slippage: float

    @property
    def total(self) -> float:
        return self.commission + self.spread + self.slippage


@dataclass(frozen=True)
class CostModel:
    version: str
    commission_bps: float
    spread_bps: float
    slippage: SlippageModel

    def __post_init__(self) -> None:
        if (
            not isfinite(self.commission_bps)
            or not isfinite(self.spread_bps)
            or self.commission_bps < 0
            or self.spread_bps < 0
        ):
            raise ValueError("cost rates must be finite and non-negative")

    def calculate(self, notional: float, *, side: str, stress_multiplier: float) -> TradeCost:
        if not isfinite(notional) or not isfinite(stress_multiplier):
            raise ValueError("notional and stress multiplier must be finite")
        if notional < 0:
            raise ValueError("notional cannot be negative")
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if stress_multiplier < 0:
            raise ValueError("stress multiplier cannot be negative")
        cost = TradeCost(
            self.version,
            notional,
            notional * self.commission_bps / 10_000,
            notional * self.spread_bps / 10_000 * stress_multiplier,
            self.slippage.calculate(notional, stress_multiplier),
        )
        if not all(
            isfinite(component) and component >= 0
            for component in (cost.commission, cost.spread, cost.slippage, cost.total)
        ):
            raise ValueError("calculated trade costs must be finite and non-negative")
        return cost
