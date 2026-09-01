from __future__ import annotations

from dataclasses import dataclass

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

    def calculate(self, notional: float, *, side: str, stress_multiplier: float) -> TradeCost:
        if notional < 0:
            raise ValueError("notional cannot be negative")
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if stress_multiplier < 0:
            raise ValueError("stress multiplier cannot be negative")
        return TradeCost(
            self.version,
            notional,
            notional * self.commission_bps / 10_000,
            notional * self.spread_bps / 10_000 * stress_multiplier,
            self.slippage.calculate(notional, stress_multiplier),
        )
