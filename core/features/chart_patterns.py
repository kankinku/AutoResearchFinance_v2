"""Causally confirmed chart geometry for Quant V3 research.

A pivot at index i is observable at i + confirmation_bars only. Signals
are emitted at bar close on that later confirmation bar; historical signals
are never backfilled. Interpretations are original bounded heuristics, not
a prediction guarantee or a proprietary harmonic implementation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import cast

PATTERNS = (
    "elliott_impulse_5",
    "elliott_abc",
    "elliott_wxy",
    "elliott_wxyxz",
    "harmonic_butterfly",
    "harmonic_gartley",
    "harmonic_bat",
    "harmonic_crab",
    "double_top",
    "double_bottom",
    "head_shoulders",
    "inverse_head_shoulders",
)


@dataclass(frozen=True)
class ConfirmedPivot:
    index: int
    value: float
    kind: str
    known_at: int


def _valid_candle(high: float | None, low: float | None, close: float | None) -> bool:
    if high is None or low is None or close is None:
        return False
    h, low_value, c = float(high), float(low), float(close)
    return all(isfinite(v) for v in (h, low_value, c)) and h >= max(low_value, c) and low_value <= c


def _signs(pivots: Sequence[ConfirmedPivot]) -> tuple[int, ...]:
    return tuple(
        1 if b.value > a.value else -1 if b.value < a.value else 0
        for a, b in zip(pivots[:-1], pivots[1:], strict=True)
    )


def impulse_five(points: Sequence[ConfirmedPivot]) -> int:
    """Only ordinary impulses; diagonals/truncated fifths are not supported."""
    if len(points) != 6:
        return 0
    for direction in (1, -1):
        p = [direction * x.value for x in points]
        if not (p[1] > p[0] and p[2] < p[1] and p[3] > p[2] and p[4] < p[3] and p[5] > p[4]):
            continue
        if not (p[2] > p[0] and p[3] > p[1] and p[4] > p[1] and p[5] > p[3]):
            continue
        w1, w3, w5 = p[1] - p[0], p[3] - p[2], p[5] - p[4]
        if w3 >= min(w1, w5):
            return direction
    return 0


def abc_three(points: Sequence[ConfirmedPivot]) -> int:
    """Zigzag-like ABC with bounded B retracement and C extension."""
    if len(points) != 4:
        return 0
    for direction in (1, -1):
        p = [direction * x.value for x in points]
        if not (p[1] > p[0] and p[2] < p[1] and p[3] > p[2]):
            continue
        a = p[1] - p[0]
        if a <= 0:
            continue
        b = (p[1] - p[2]) / a
        c = (p[3] - p[2]) / a
        if 0.236 <= b <= 1.05 and 0.618 <= c <= 1.90 and p[3] > p[0]:
            return direction
    return 0


def complex_correction(points: Sequence[ConfirmedPivot], count: int) -> int:
    """W-X-Y or W-X-Y-X-Z, with each named unit restricted to an ABC zigzag."""
    if count not in (3, 5) or len(points) != 3 * count + 1:
        return 0
    directions = [abc_three(points[3 * i : 3 * i + 4]) for i in range(count)]
    if directions[0] and all(
        directions[i] == directions[0] * (1 if i % 2 == 0 else -1) for i in range(count)
    ):
        return directions[0]
    return 0


def harmonic_xabcd(points: Sequence[ConfirmedPivot], pattern: str, tolerance: float = 0.09) -> int:
    """Original approximate XA/AB/BC/CD ratio gates for four harmonic families."""
    if len(points) != 5 or pattern not in {
        "harmonic_butterfly",
        "harmonic_gartley",
        "harmonic_bat",
        "harmonic_crab",
    }:
        return 0
    signs = _signs(points)
    if signs not in ((1, -1, 1, -1), (-1, 1, -1, 1)):
        return 0
    x, a, b, c, d = (point.value for point in points)
    xa, ab, bc, cd = abs(a - x), abs(b - a), abs(c - b), abs(d - c)
    if min(xa, ab, bc, cd) <= 1e-9:
        return 0
    br, cr = ab / xa, bc / ab
    if not 0.382 - tolerance <= cr <= 0.886 + tolerance:
        return 0
    beyond_x = d < x if signs[0] == 1 else d > x
    between_xa = min(x, a) < d < max(x, a)

    def near(value: float, target: float) -> bool:
        return abs(value - target) <= tolerance

    if pattern == "harmonic_butterfly":
        valid = beyond_x and near(br, 0.786) and near(abs(d - x) / xa, 0.27) and cd / bc >= 1.13
    elif pattern == "harmonic_gartley":
        valid = between_xa and near(br, 0.618) and near(abs(a - d) / xa, 0.786)
    elif pattern == "harmonic_bat":
        valid = (
            between_xa
            and 0.382 - tolerance <= br <= 0.5 + tolerance
            and near(abs(a - d) / xa, 0.886)
        )
    else:
        valid = (
            beyond_x
            and 0.382 - tolerance <= br <= 0.618 + tolerance
            and near(abs(d - x) / xa, 0.618)
        )
    return signs[0] if valid else 0


def classical_shape(points: Sequence[ConfirmedPivot], pattern: str) -> int:
    if pattern in {"double_top", "double_bottom"} and len(points) == 3:
        a, b, c = (p.value for p in points)
        if min(abs(a), abs(c)) <= 1e-9:
            return 0
        peaks_close = abs(a - c) / max(abs(a), abs(c)) <= 0.035
        if pattern == "double_top" and a > b and c > b and peaks_close:
            return -1 if (min(a, c) - b) / max(abs(a), abs(c)) >= 0.025 else 0
        if pattern == "double_bottom" and a < b and c < b and peaks_close:
            return 1 if (b - max(a, c)) / max(abs(a), abs(c)) >= 0.025 else 0
    if pattern in {"head_shoulders", "inverse_head_shoulders"} and len(points) == 5:
        direction = 1 if pattern == "head_shoulders" else -1
        a, b, c, d, e = (direction * p.value for p in points)
        if min(abs(a), abs(e)) <= 1e-9:
            return 0
        if (
            c > max(a, e) * 1.03
            and abs(a - e) / max(abs(a), abs(e)) <= 0.05
            and b < min(a, c)
            and d < min(c, e)
            and abs(b - d) / max(abs(b), abs(d), 1) <= 0.06
        ):
            return -direction
    return 0


def _recognize(pattern: str, pivots: Sequence[ConfirmedPivot]) -> int:
    if pattern == "elliott_impulse_5":
        return impulse_five(pivots[-6:])
    if pattern == "elliott_abc":
        return abc_three(pivots[-4:])
    if pattern == "elliott_wxy":
        return complex_correction(pivots[-10:], 3)
    if pattern == "elliott_wxyxz":
        return complex_correction(pivots[-16:], 5)
    if pattern.startswith("harmonic_"):
        return harmonic_xabcd(pivots[-5:], pattern)
    if pattern.endswith("shoulders"):
        return classical_shape(pivots[-5:], pattern)
    return classical_shape(pivots[-3:], pattern)


def calculate_chart_pattern(
    inputs: Mapping[str, Sequence[float | None]],
    pattern: str,
    lookback: int = 160,
    confirmation_bars: int = 2,
    minimum_swing: float = 0.015,
) -> tuple[float | None, ...]:
    """One -1/0/+1 event at the newly confirmed last pivot, never backfilled."""
    if pattern not in PATTERNS:
        raise ValueError(f"unknown chart pattern: {pattern}")
    if not (32 <= lookback <= 252 and 1 <= confirmation_bars <= 6 and 0 < minimum_swing <= 0.25):
        raise ValueError("bounded causal chart pattern parameters required")
    high, low, close = (inputs[key] for key in ("high", "low", "close"))
    count = len(close)
    if len(high) != count or len(low) != count:
        raise ValueError("unaligned OHLC")
    pivots: list[ConfirmedPivot] = []
    output: list[float | None] = [0.0] * count
    for t in range(count):
        candidate = t - confirmation_bars
        if candidate < confirmation_bars:
            continue
        first = candidate - confirmation_bars
        interval = range(first, t + 1)
        if not all(_valid_candle(high[j], low[j], close[j]) for j in interval):
            pivots.clear()
            continue
        highs = [float(cast(float, high[j])) for j in interval]
        lows = [float(cast(float, low[j])) for j in interval]
        center = confirmation_bars
        is_high = highs[center] == max(highs) and highs.count(highs[center]) == 1
        is_low = lows[center] == min(lows) and lows.count(lows[center]) == 1
        if is_high == is_low:
            continue
        kind = "high" if is_high else "low"
        price = highs[center] if is_high else lows[center]
        pivot = ConfirmedPivot(candidate, price, kind, t)
        pivots = [p for p in pivots if p.index >= t - lookback]
        if pivots and pivots[-1].kind == kind:
            before = pivots[-1]
            more_extreme = price > before.value if is_high else price < before.value
            if more_extreme:
                pivots[-1] = pivot
            continue
        if (
            pivots
            and abs(price - pivots[-1].value) / max(abs(pivots[-1].value), 1e-9) < minimum_swing
        ):
            continue
        pivots.append(pivot)
        decision = _recognize(pattern, pivots)
        if decision:
            output[t] = float(decision)
    return tuple(output)
