from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class SlippageModel:
    basis_points: float

    def __post_init__(self) -> None:
        if not isfinite(self.basis_points) or self.basis_points < 0:
            raise ValueError("slippage must be finite and non-negative")

    def calculate(self, notional: float, stress_multiplier: float) -> float:
        return notional * self.basis_points / 10_000 * stress_multiplier
