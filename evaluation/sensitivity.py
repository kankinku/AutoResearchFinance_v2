from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, pstdev


@dataclass(frozen=True)
class SensitivityReport:
    status: str
    ranges: dict[str, tuple[float, float]]
    importance: dict[str, float]
    stability: float


def parameter_sensitivity(scores: dict[str, dict[float, float]]) -> SensitivityReport:
    if not scores or any(len(values) < 2 for values in scores.values()):
        return SensitivityReport("INSUFFICIENT_EVIDENCE", {}, {}, 0.0)
    ranges = {
        name: (min(values), max(values)) for name, values in sorted(scores.items())
    }
    importance = {
        name: pstdev(values.values()) for name, values in sorted(scores.items())
    }
    normalized = [1 / (1 + value) for value in importance.values()]
    return SensitivityReport("OK", ranges, importance, fmean(normalized))
