from __future__ import annotations


class PlateauDetector:
    def __init__(self, *, patience: int, min_delta: float) -> None:
        if patience <= 0 or min_delta < 0:
            raise ValueError("patience must be positive and min_delta cannot be negative")
        self.patience = patience
        self.min_delta = min_delta
        self._best: float | None = None
        self._without_improvement = 0

    def observe(self, score: float) -> bool:
        if self._best is None or score > self._best + self.min_delta:
            self._best = score
            self._without_improvement = 0
            return False
        self._without_improvement += 1
        return self._without_improvement >= self.patience
