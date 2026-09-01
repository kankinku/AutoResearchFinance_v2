from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlippageModel:
    basis_points: float

    def __post_init__(self) -> None:
        if self.basis_points < 0:
            raise ValueError("slippage cannot be negative")

    def calculate(self, notional: float, stress_multiplier: float) -> float:
        return notional * self.basis_points / 10_000 * stress_multiplier
