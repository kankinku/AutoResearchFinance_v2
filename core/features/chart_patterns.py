"""Causally confirmed chart geometry for Quant V3 research.

A pivot at index i is observable at i + confirmation_bars only. Signals
are emitted at bar close on that later confirmation bar; historical signals
are never backfilled. Interpretations are original bounded heuristics, not
a prediction guarantee or a proprietary harmonic implementation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.features.causal_pivots import CausalSwingConfig, CausalSwingTracker, ConfirmedPivot

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


def harmonic_xabcd(
    points: Sequence[ConfirmedPivot],
    pattern: str,
    tolerance: float = 0.09,
) -> int:
    """Signed scalar adapter to the provenance-tracked A5 harmonic validator.

    The legacy default tolerance is retained for call compatibility.
    A custom tolerance is rejected rather than silently changing/ignoring
    source-grounded independent ratio gates.
    """
    from core.features.harmonic_geometry import RULES, assess_harmonic

    if tolerance != 0.09:
        raise ValueError("A5 source ratio rules do not support tolerance overrides")
    if pattern not in RULES:
        return 0
    return int(assess_harmonic(points, pattern).direction)


def classical_shape(points: Sequence[ConfirmedPivot], pattern: str) -> int:
    if pattern == "inverse_head_shoulders":
        # A7: negative-value mirroring in the old head comparison could
        # accept equal-height shoulders/head as an inverse H&S pattern.
        from core.features.classical_lifecycle import assess_classical_candidate

        candidate = assess_classical_candidate(points, pattern)
        return int(candidate.direction) if candidate else 0
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
    config = CausalSwingConfig(
        confirmation_bars=confirmation_bars,
        lookback=lookback,
        minimum_swing=minimum_swing,
        mode="percent",
    )
    high, low, close = (inputs[key] for key in ("high", "low", "close"))
    count = len(close)
    if len(high) != count or len(low) != count:
        raise ValueError("unaligned OHLC")
    tracker = CausalSwingTracker(config)
    output: list[float | None] = [0.0] * count
    for t in range(count):
        decision = tracker.update(t, high[t], low[t], close[t])
        # A more extreme replacement changes *current pivot state* but must
        # NOT retroactively publish a newly recognized pattern at old time.
        if decision is not None and decision.kind == "APPEND":
            detected = _recognize(pattern, tracker.pivots)
            if detected:
                output[t] = float(detected)
    return tuple(output)
