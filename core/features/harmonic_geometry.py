"""Research-only XABCD geometric screening; no licensed third-party source code.

These numerical checks use public ratio references attributed per pattern.
Pattern names are held for provenance; commercial trademark permissions have
NOT been obtained. A PRZ is a geometric region, not a trade instruction.
Only confirmed five-point structures are labeled as positive.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType

from core.features.causal_pivots import ConfirmedPivot

RATIO_EPS = 1e-10  # Stability only, not an adjustable Fibonacci tolerance


@dataclass(frozen=True)
class HarmonicRule:
    name: str
    source_url: str
    b_min: float
    b_max: float
    xa_at_d: float
    xa_tolerance: float
    bc_min: float
    bc_max: float
    bc_retrace_min: float = 0.382
    bc_retrace_max: float = 0.886
    # Optional AB=CD alternatives, checked with an absolute tolerance on ratios.
    cd_over_ab_targets: tuple[float, ...] = ()
    cd_over_ab_tolerance: float = 0.15
    # Crab's extended CD/AB can exceed all the usual alternate AB=CD targets.
    abcd_minimum_only: bool = False


RULES: Mapping[str, HarmonicRule] = MappingProxyType(
    {
        "harmonic_gartley": HarmonicRule(
            name="harmonic_gartley",
            source_url="https://harmonictrader.com/harmonicpatternorigin/",
            b_min=0.618 * 0.97,
            b_max=0.618 * 1.03,
            xa_at_d=0.786,
            xa_tolerance=0.035,
            bc_min=1.13,
            bc_max=1.618,
            cd_over_ab_targets=(1.0, 1.27),
            cd_over_ab_tolerance=0.15,
        ),
        "harmonic_butterfly": HarmonicRule(
            name="harmonic_butterfly",
            source_url="https://harmonictrader.com/harmonic-patterns/butterfly-pattern/",
            b_min=0.751,
            b_max=0.821,
            xa_at_d=1.27,
            xa_tolerance=0.035,
            bc_min=1.618,
            bc_max=2.618,
            cd_over_ab_targets=(1.0, 1.27, 1.618),
            cd_over_ab_tolerance=0.14,
        ),
        "harmonic_bat": HarmonicRule(
            name="harmonic_bat",
            source_url="https://harmonictrader.com/harmonic-patterns/bat-pattern/",
            b_min=0.362,
            b_max=0.52,
            xa_at_d=0.886,
            xa_tolerance=0.035,
            bc_min=1.618,
            bc_max=2.618,
            cd_over_ab_targets=(1.0, 1.27, 1.618),
            cd_over_ab_tolerance=0.18,
        ),
        "harmonic_crab": HarmonicRule(
            name="harmonic_crab",
            source_url="https://harmonictrader.com/harmonic-patterns/crab-pattern/",
            b_min=0.362,
            b_max=0.638,
            xa_at_d=1.618,
            xa_tolerance=0.035,
            bc_min=2.24,
            bc_max=3.618,
            abcd_minimum_only=True,
        ),
    }
)


@dataclass(frozen=True)
class HarmonicAssessment:
    name: str
    stage: str
    direction: int
    accepted: bool
    ratios: Mapping[str, float]
    failed_rules: tuple[str, ...]
    prz_low: float
    prz_high: float
    source_url: str
    commercial_license: str = "NOT_CLEARED"


def _points(points: Sequence[ConfirmedPivot], minimum: int) -> tuple[tuple[float, ...], int] | None:
    if len(points) != minimum:
        return None
    prices = tuple(float(p.value) for p in points)
    if not all(isfinite(x) for x in prices):
        return None
    if any(not left.index < right.index for left, right in zip(points, points[1:], strict=False)):
        return None
    signs = tuple(
        1 if nxt > prev else -1 if nxt < prev else 0
        for prev, nxt in zip(prices, prices[1:], strict=False)
    )
    bullish = tuple(1 if i % 2 == 0 else -1 for i in range(len(prices) - 1))
    bearish = tuple(-x for x in bullish)
    if signs == bullish:
        return prices, 1
    if signs == bearish:
        return prices, -1
    return None


def _zone(
    first_four: Sequence[float], direction: int, rule: HarmonicRule
) -> tuple[float, float] | None:
    x, a, b, c = first_four
    xa = abs(a - x)
    ab = abs(b - a)
    bc = abs(c - b)
    if min(xa, ab, bc) <= 1e-9:
        return None
    b_ratio = ab / xa
    c_ratio = bc / ab
    if not (rule.b_min - RATIO_EPS <= b_ratio <= rule.b_max + RATIO_EPS):
        return None
    if not (rule.bc_retrace_min - RATIO_EPS <= c_ratio <= rule.bc_retrace_max + RATIO_EPS):
        return None
    # For a completed bullish W, D extends down from A and C; for a bearish
    # M, it extends up. Intersect XA and BC-derived reversal intervals.
    target = a - direction * rule.xa_at_d * xa
    xa_low = target - xa * rule.xa_tolerance
    xa_high = target + xa * rule.xa_tolerance
    bc_price1 = c - direction * rule.bc_min * bc
    bc_price2 = c - direction * rule.bc_max * bc
    low = max(xa_low, min(bc_price1, bc_price2))
    high = min(xa_high, max(bc_price1, bc_price2))
    if low > high + xa * RATIO_EPS:
        return None
    return low, high


def projected_reversal_zone(
    points: Sequence[ConfirmedPivot], name: str
) -> tuple[float, float] | None:
    """Pre-D numerical zone only; cannot confirm a trade or signal."""
    rule = RULES.get(name)
    if rule is None:
        raise ValueError(f"unknown harmonic rule: {name}")
    values = _points(points, 4)
    if values is None:
        return None
    prices, direction = values
    return _zone(prices, direction, rule)


def assess_harmonic(points: Sequence[ConfirmedPivot], name: str) -> HarmonicAssessment:
    """Require independent XA, AB, BC, CD/AB and PRZ gates at D."""
    rule = RULES.get(name)
    if rule is None:
        raise ValueError(f"unknown harmonic rule: {name}")
    values = _points(points, 5)
    if values is None:
        return HarmonicAssessment(
            name,
            "REJECTED",
            0,
            False,
            {},
            ("XABCD_GEOMETRY",),
            0.0,
            0.0,
            rule.source_url,
        )
    (x, a, b, c, d), direction = values
    xa, ab, bc, cd = abs(a - x), abs(b - a), abs(c - b), abs(d - c)
    if min(xa, ab, bc, cd) <= 1e-9:
        return HarmonicAssessment(
            name,
            "REJECTED",
            0,
            False,
            {},
            ("ZERO_LENGTH_LEG",),
            0.0,
            0.0,
            rule.source_url,
        )
    ratios = {
        "AB/XA": ab / xa,
        "BC/AB": bc / ab,
        "CD/BC": cd / bc,
        "CD/AB": cd / ab,
        "AD/XA": abs(a - d) / xa,
    }
    failed: list[str] = []
    if not rule.b_min - RATIO_EPS <= ratios["AB/XA"] <= rule.b_max + RATIO_EPS:
        failed.append("AB/XA")
    if not rule.bc_retrace_min - RATIO_EPS <= ratios["BC/AB"] <= rule.bc_retrace_max + RATIO_EPS:
        failed.append("BC/AB")
    if not rule.bc_min - RATIO_EPS <= ratios["CD/BC"] <= rule.bc_max + RATIO_EPS:
        failed.append("CD/BC")
    if abs(ratios["AD/XA"] - rule.xa_at_d) > rule.xa_tolerance + RATIO_EPS:
        failed.append("AD/XA")
    if rule.abcd_minimum_only:
        if ratios["CD/AB"] < 1.0 - RATIO_EPS:
            failed.append("CD/AB")
    elif not any(
        abs(ratios["CD/AB"] - target) <= rule.cd_over_ab_tolerance + RATIO_EPS
        for target in rule.cd_over_ab_targets
    ):
        failed.append("CD/AB")
    zone = _zone((x, a, b, c), direction, rule)
    if zone is None or not zone[0] - xa * RATIO_EPS <= d <= zone[1] + xa * RATIO_EPS:
        failed.append("PRZ")
    return HarmonicAssessment(
        name=name,
        stage="CONFIRMED" if not failed else "REJECTED",
        direction=direction if not failed else 0,
        accepted=not failed,
        ratios=ratios,
        failed_rules=tuple(failed),
        prz_low=zone[0] if zone else 0.0,
        prz_high=zone[1] if zone else 0.0,
        source_url=rule.source_url,
    )
