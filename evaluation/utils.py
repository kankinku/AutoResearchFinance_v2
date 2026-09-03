from __future__ import annotations


def clamp_unit(value: float) -> float:
    """Clamp a metric to the closed unit interval."""

    return max(0.0, min(1.0, value))
