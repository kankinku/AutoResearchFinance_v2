from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean


@dataclass(frozen=True)
class RegimeStats:
    count: int
    mean_return: float
    win_rate: float


@dataclass(frozen=True)
class RegimeReport:
    status: str
    by_regime: dict[str, RegimeStats]


def regime_breakdown(regimes: tuple[str, ...], returns: tuple[float, ...]) -> RegimeReport:
    if len(regimes) != len(returns) or len(set(regimes)) < 2:
        return RegimeReport("INSUFFICIENT_EVIDENCE", {})
    grouped: dict[str, list[float]] = {}
    for regime, value in zip(regimes, returns, strict=True):
        grouped.setdefault(regime, []).append(value)
    report = {
        regime: RegimeStats(
            len(values), fmean(values), sum(value > 0 for value in values) / len(values)
        )
        for regime, values in sorted(grouped.items())
    }
    return RegimeReport("OK", report)
