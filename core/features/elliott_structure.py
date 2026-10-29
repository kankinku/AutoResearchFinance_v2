"""A6 research-only causal Elliott wave diagnostics (not trade signals).

Outer pivot sequences express provisional *hypotheses*. The named 5-3-5-3-5
impulse, 5-3-5 zigzag and 3-3-5 flat are marked structurally_verified ONLY
when explicitly observed subordinate confirmed pivots support each segment.
No future subwaves or post-hoc prices are accepted as prior knowledge.

This does not exhaust Elliott alternatives (diagonals, truncated fifths,
running flats, triangles and ambiguous wave degrees require later research).
Source attribution: https://www.elliottwave.com/waveopedia/impulse/
https://www.elliottwave.com/waveopedia/zigzags/
https://www.elliottwave.com/waveopedia/flats/
No copyrighted source code was copied.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from core.features.causal_pivots import ConfirmedPivot

Stage = Literal["INSUFFICIENT", "DEVELOPING", "CONFIRMED", "INVALIDATED"]
ELLIOTT_STAGE: tuple[Stage, ...] = (
    "INSUFFICIENT",
    "DEVELOPING",
    "CONFIRMED",
    "INVALIDATED",
)

# A segment's subordinate turning points, including its exact endpoints.
Leg = Sequence[ConfirmedPivot]
Nested = Sequence[Leg]


@dataclass(frozen=True)
class WaveAssessment:
    family: str
    subtype: str
    stage: Stage
    direction: int
    wave_number: int
    known_at: int | None
    eligible_on_next_bar: int | None
    structurally_verified: bool
    violations: tuple[str, ...]
    alternative_counts: tuple[str, ...]
    pivot_indices: tuple[int, ...]
    invalidation_price: float | None
    # Observed counts are descriptive, not posterior probabilities.
    degree: str = "UNRESOLVED"


def _check_pivots(
    points: Sequence[ConfirmedPivot], decision_at: int | None
) -> tuple[int | None, tuple[str, ...]]:
    if not points:
        return None, ()
    if any(not isfinite(float(p.value)) for p in points):
        return None, ("NON_FINITE",)
    if any(
        a.index >= b.index or a.known_at > b.known_at
        for a, b in zip(points, points[1:], strict=False)
    ):
        return None, ("NON_MONOTONIC_PIVOTS",)
    known = max(p.known_at for p in points)
    if decision_at is not None and known > decision_at:
        raise ValueError("cannot use an Elliott pivot before it becomes known")
    return known, ()


def _build(
    family: str,
    subtype: str,
    stage: Stage,
    points: Sequence[ConfirmedPivot],
    direction: int,
    verified: bool,
    violations: tuple[str, ...] = (),
    alternatives: tuple[str, ...] = (),
    count: int | None = None,
    invalidation_price: float | None = None,
) -> WaveAssessment:
    known = max((p.known_at for p in points), default=None)
    return WaveAssessment(
        family=family,
        subtype=subtype,
        stage=stage,
        direction=direction,
        wave_number=count if count is not None else max(0, len(points) - 1),
        known_at=known,
        eligible_on_next_bar=known + 1 if known is not None else None,
        structurally_verified=verified,
        violations=violations,
        alternative_counts=alternatives[:3],
        pivot_indices=tuple(p.index for p in points),
        invalidation_price=invalidation_price,
    )


def _subdivisions(
    outer: Sequence[ConfirmedPivot],
    nested: Nested,
    counts: tuple[int, ...],
    decision_at: int,
) -> tuple[str, ...]:
    """Validate observed fine turning points, exact boundaries and timing."""
    if len(outer) != len(counts) + 1 or len(nested) != len(counts):
        return ("SUBWAVE_TOPOLOGY",)
    errors: list[str] = []
    for i, required in enumerate(counts):
        leg = nested[i]
        if len(leg) != required + 1:
            errors.append("SUBWAVE_TOPOLOGY")
            continue
        if leg[0] != outer[i] or leg[-1] != outer[i + 1]:
            errors.append("SUBWAVE_TOPOLOGY")
            continue
        if any(p.known_at > decision_at for p in leg):
            errors.append("SUBWAVE_NOT_KNOWN")
            continue
        if any(not isfinite(p.value) for p in leg):
            errors.append("SUBWAVE_TOPOLOGY")
            continue
        if any(
            x.index >= y.index or x.known_at > y.known_at
            for x, y in zip(leg, leg[1:], strict=False)
        ):
            errors.append("SUBWAVE_TOPOLOGY")
            continue
        direction = 1 if outer[i + 1].value > outer[i].value else -1
        changes = [y.value - x.value for x, y in zip(leg, leg[1:], strict=False)]
        if any(
            delta * direction * (1 if j % 2 == 0 else -1) <= 0 for j, delta in enumerate(changes)
        ):
            errors.append("SUBWAVE_TOPOLOGY")
    return tuple(dict.fromkeys(errors))


def analyze_impulse(
    points: Sequence[ConfirmedPivot],
    *,
    decision_at: int | None = None,
    subwaves: Nested | None = None,
) -> WaveAssessment:
    """Outer wave 1..5 rule gate; inner 5-3-5-3-5 verified only if supplied."""
    family = "IMPULSE"
    if len(points) > 6:
        raise ValueError("impulse requires at most six ordered outer pivots")
    known, err = _check_pivots(points, decision_at)
    if err:
        return _build(family, "ORDINARY", "INVALIDATED", points, 0, False, err)
    if len(points) < 2:
        return _build(family, "ORDINARY", "INSUFFICIENT", points, 0, False)
    direction = 1 if points[1].value > points[0].value else -1
    oriented = [direction * p.value for p in points]
    n = len(points) - 1
    violations: list[str] = []
    # Each segment alternates actionary/reactionary direction.
    if any((oriented[i + 1] - oriented[i]) * (1 if i % 2 == 0 else -1) <= 0 for i in range(n)):
        violations.append("ALTERNATION")
    if n >= 2 and oriented[2] <= oriented[0]:
        violations.append("WAVE2_RETRACE_ORIGIN")
    if n >= 3 and oriented[3] <= oriented[1]:
        violations.append("WAVE3_NOT_ADVANCING")
    if n >= 4 and oriented[4] <= oriented[1]:
        violations.append("WAVE4_OVERLAPS_1")
    if n >= 5:
        if oriented[5] <= oriented[3]:
            violations.append("WAVE5_NOT_ADVANCING")
        wave1 = oriented[1] - oriented[0]
        wave3 = oriented[3] - oriented[2]
        wave5 = oriented[5] - oriented[4]
        if wave3 < min(wave1, wave5):
            violations.append("WAVE3_SHORTEST")
    checked = False
    if subwaves is not None:
        if len(subwaves) != n:
            violations.append("SUBWAVE_TOPOLOGY")
        else:
            expected = (5, 3, 5, 3, 5)[:n]
            errs = _subdivisions(points, subwaves, expected, known or 0)
            violations.extend(errs)
            checked = not bool(errs) and n == 5
    stage: Stage = "INVALIDATED" if violations else "CONFIRMED" if n == 5 else "DEVELOPING"
    alternatives = ("OUTER_IMPULSE", "ZIGZAG_ABC_POSSIBLE") if n >= 3 else ("OUTER_IMPULSE",)
    invalidation = points[0].value if n <= 2 else points[1].value if n >= 4 else None
    return _build(
        family,
        "ORDINARY",
        stage,
        points,
        direction,
        checked and not violations,
        tuple(dict.fromkeys(violations)),
        alternatives,
        invalidation_price=invalidation,
    )


def analyze_abc(
    points: Sequence[ConfirmedPivot],
    subwaves: Nested | None = None,
    *,
    decision_at: int | None = None,
) -> WaveAssessment:
    """Zigzag 5-3-5 vs regular flat 3-3-5; both need nested proof."""
    if len(points) != 4:
        raise ValueError("ABC requires exactly four outer turning points")
    known, err = _check_pivots(points, decision_at)
    if err:
        return _build("ABC", "UNKNOWN", "INVALIDATED", points, 0, False, err)
    direction = 1 if points[1].value > points[0].value else -1
    p = [direction * x.value for x in points]
    if p[1] <= p[0] or p[2] >= p[1] or p[3] <= p[2]:
        return _build(
            "ABC",
            "UNKNOWN",
            "INVALIDATED",
            points,
            direction,
            False,
            ("ABC_DIRECTION",),
        )
    amplitude = p[1] - p[0]
    b_ratio = (p[1] - p[2]) / amplitude
    c_ratio = (p[3] - p[2]) / amplitude
    if not (0.236 <= b_ratio <= 1.38 and 0.618 <= c_ratio <= 2.0):
        return _build(
            "ABC",
            "UNKNOWN",
            "INVALIDATED",
            points,
            direction,
            False,
            ("ABC_FAMILY_RATIO",),
        )
    if subwaves is None:
        return _build(
            "ABC",
            "OUTER_ONLY",
            "DEVELOPING",
            points,
            direction,
            False,
            alternatives=("ZIGZAG", "FLAT"),
        )
    counts = tuple(len(leg) - 1 for leg in subwaves)
    family = "ZIGZAG" if counts == (5, 3, 5) else "FLAT" if counts == (3, 3, 5) else "UNKNOWN"
    if family == "UNKNOWN":
        return _build(
            "ABC",
            "UNKNOWN",
            "INVALIDATED",
            points,
            direction,
            False,
            ("SUBWAVE_TOPOLOGY",),
        )
    if (family == "ZIGZAG" and not 0.236 <= b_ratio <= 0.786) or (
        family == "FLAT" and not 0.9 <= b_ratio <= 1.38
    ):
        return _build(
            "ABC",
            family,
            "INVALIDATED",
            points,
            direction,
            False,
            ("ABC_FAMILY_RATIO",),
        )
    errors = _subdivisions(points, subwaves, counts, known or 0)
    return _build(
        "ABC",
        family,
        "CONFIRMED" if not errors else "INVALIDATED",
        points,
        direction,
        not bool(errors),
        errors,
        alternatives=(family,),
    )


def analyze_combination(
    points: Sequence[ConfirmedPivot],
    components: Sequence[Nested],
    *,
    count: Literal[3, 5],
    decision_at: int | None = None,
) -> WaveAssessment:
    """W-X-Y or W-X-Y-X-Z; 3 ABC groups per correction, causal nested evidence."""
    if count not in (3, 5) or len(points) != count * 3 + 1:
        raise ValueError("WXY/WXYXZ outer pivot count mismatch")
    known, err = _check_pivots(points, decision_at)
    family = "W-X-Y" if count == 3 else "W-X-Y-X-Z"
    if err:
        return _build("COMBINATION", family, "INVALIDATED", points, 0, False, err)
    direction = 1 if points[3].value > points[0].value else -1
    if len(components) < count:
        return _build(
            "COMBINATION",
            family,
            "DEVELOPING",
            points,
            direction,
            False,
            alternatives=("ZIGZAG_COMBINATION", "FLAT_COMBINATION"),
            count=count,
        )
    if len(components) > count:
        return _build(
            "COMBINATION",
            family,
            "INVALIDATED",
            points,
            direction,
            False,
            ("COMPONENT_COUNT",),
            count=count,
        )
    violations: list[str] = []
    verified: list[WaveAssessment] = []
    for i in range(count):
        piece = points[3 * i : 3 * i + 4]
        part = analyze_abc(piece, components[i], decision_at=known)
        expected_dir = direction if i % 2 == 0 else -direction
        if part.direction != expected_dir or part.stage != "CONFIRMED":
            violations.append("CONNECTOR_MISMATCH")
        violations.extend(part.violations)
        verified.append(part)
    if any(points[3 * i + 3].value == points[3 * i].value for i in range(count)):
        violations.append("ZERO_NET_COMPONENT")
    return _build(
        "COMBINATION",
        family,
        "INVALIDATED" if violations else "CONFIRMED",
        points,
        direction,
        not violations and all(u.structurally_verified for u in verified),
        tuple(dict.fromkeys(violations)),
        alternatives=(family, "DEGREE_AMBIGUOUS"),
        count=count,
    )


class WaveHypothesisStream:
    """Append-only, bounded-alternatives wave-count evidence; research only."""

    def __init__(self, max_alternatives: int = 3) -> None:
        if not 1 <= max_alternatives <= 3:
            raise ValueError("bounded alternatives must be 1..3")
        self._pivots: list[ConfirmedPivot] = []
        self._history: list[WaveAssessment] = []
        self.max_alternatives = max_alternatives

    @property
    def history(self) -> tuple[WaveAssessment, ...]:
        return tuple(self._history)

    def ingest(self, pivot: ConfirmedPivot) -> WaveAssessment:
        _check_pivots((*self._pivots, pivot), pivot.known_at)
        if self._pivots and (
            pivot.index <= self._pivots[-1].index or pivot.known_at <= self._pivots[-1].known_at
        ):
            raise ValueError("unsequenced or repeated confirmed pivot")
        self._pivots.append(pivot)
        if len(self._pivots) > 6:
            self._pivots.pop(0)
        result = analyze_impulse(self._pivots, decision_at=pivot.known_at)
        if len(result.alternative_counts) > self.max_alternatives:
            from dataclasses import replace

            result = replace(
                result, alternative_counts=result.alternative_counts[: self.max_alternatives]
            )
        self._history.append(result)
        return result


def derive_subwaves(
    outer: Sequence[ConfirmedPivot],
    fine: Sequence[ConfirmedPivot],
    counts: tuple[int, ...],
    *,
    decision_at: int | None = None,
) -> tuple[tuple[ConfirmedPivot, ...], ...] | None:
    """Bind two causal pivot scales only when every nested leg is observable.

    No interpolation or synthetic inner swings. We require exact outer
    turning-point alignment in the finer stream; a missing pivot leaves
    the macro structure *unverified*, never guessed from future bars.
    """
    known, errors = _check_pivots(outer, decision_at)
    if errors or known is None or len(counts) != len(outer) - 1:
        return None
    observation = known if decision_at is None else decision_at
    ordered = tuple(p for p in fine if p.known_at <= observation)
    _, fine_errors = _check_pivots(ordered, observation)
    if fine_errors:
        return None
    result: list[tuple[ConfirmedPivot, ...]] = []
    for i, expected in enumerate(counts):
        left, right = outer[i], outer[i + 1]
        leg = tuple(p for p in ordered if left.index <= p.index <= right.index)
        if len(leg) != expected + 1 or leg[0] != left or leg[-1] != right:
            return None
        result.append(leg)
    nested = tuple(result)
    if _subdivisions(outer, nested, counts, observation):
        return None
    return nested


def analyze_multiscale_impulse(
    outer: Sequence[ConfirmedPivot],
    finer: Sequence[ConfirmedPivot],
    *,
    decision_at: int | None = None,
) -> WaveAssessment:
    """Opt-in dual-scale evidence: unaligned fine pivots cannot verify structure."""
    if not outer:
        return analyze_impulse(outer, decision_at=decision_at)
    counts = (5, 3, 5, 3, 5)[: max(0, len(outer) - 1)]
    nested = derive_subwaves(outer, finer, counts, decision_at=decision_at)
    return analyze_impulse(outer, decision_at=decision_at, subwaves=nested)


def analyze_multiscale_abc(
    outer: Sequence[ConfirmedPivot],
    finer: Sequence[ConfirmedPivot],
    *,
    decision_at: int | None = None,
) -> WaveAssessment:
    """Try supported ABC families; keep alternative if neither is observed."""
    for counts in ((5, 3, 5), (3, 3, 5)):
        nested = derive_subwaves(outer, finer, counts, decision_at=decision_at)
        if nested is not None:
            return analyze_abc(outer, nested, decision_at=decision_at)
    return analyze_abc(outer, decision_at=decision_at)
