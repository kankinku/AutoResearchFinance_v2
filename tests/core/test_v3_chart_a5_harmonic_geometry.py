"""A5: source-grounded XABCD ratio, PRZ and causal signed research output tests."""

from __future__ import annotations

import math

import pytest

from core.features.causal_pivots import ConfirmedPivot
from core.features.chart_patterns import calculate_chart_pattern, harmonic_xabcd
from core.features.harmonic_geometry import assess_harmonic, projected_reversal_zone

VALID = {
    "harmonic_gartley": (100.0, 120.0, 107.64, 115.0, 104.28),
    "harmonic_butterfly": (100.0, 120.0, 104.28, 114.0, 94.60),
    "harmonic_bat": (100.0, 120.0, 110.0, 115.0, 102.28),
    "harmonic_crab": (100.0, 120.0, 110.0, 118.86, 87.64),
}
INVALID = {
    "harmonic_gartley": (100.0, 120.0, 107.64, 112.4, 104.28),  # BC extension 1.706 > 1.618
    "harmonic_butterfly": (100.0, 120.0, 104.28, 109.0, 94.6),  # CD/BC 3.05 > 2.618
    "harmonic_bat": (100.0, 120.0, 107.0, 113.5, 102.28),  # B/XA .65 >= .618
    "harmonic_crab": (100.0, 120.0, 110.0, 115.0, 87.64),  # CD/BC 5.472 > 3.618
}


def points(values: tuple[float, ...]) -> list[ConfirmedPivot]:
    return [
        ConfirmedPivot(i, value, "high" if i % 2 else "low", i + 2)
        for i, value in enumerate(values)
    ]


@pytest.mark.parametrize("pattern", sorted(VALID))  # type: ignore[untyped-decorator]
@pytest.mark.parametrize("reflection", (False, True))  # type: ignore[untyped-decorator]
def test_valid_source_ratios_are_signed_and_mirror_symmetric(
    pattern: str, reflection: bool
) -> None:
    sample: tuple[float, ...] = VALID[pattern]
    if reflection:
        sample = tuple(220 - x for x in sample)
    result = assess_harmonic(points(sample), pattern)
    assert result.accepted and result.stage == "CONFIRMED", (pattern, result)
    assert result.direction == (-1 if reflection else 1)
    assert result.failed_rules == ()
    assert result.source_url.startswith("https://harmonictrader.com/")
    assert result.prz_low <= sample[4] <= result.prz_high
    assert harmonic_xabcd(points(sample), pattern) == result.direction
    assert result.ratios["CD/BC"] >= 1.13


@pytest.mark.parametrize("pattern", sorted(INVALID))  # type: ignore[untyped-decorator]
def test_invalid_ratio_rejected_with_specific_gate(pattern: str) -> None:
    result = assess_harmonic(points(INVALID[pattern]), pattern)
    assert not result.accepted
    assert result.failed_rules
    assert harmonic_xabcd(points(INVALID[pattern]), pattern) == 0
    expected = {
        "harmonic_gartley": "CD/BC",
        "harmonic_butterfly": "CD/BC",
        "harmonic_bat": "AB/XA",
        "harmonic_crab": "CD/BC",
    }
    assert expected[pattern] in result.failed_rules


@pytest.mark.parametrize("pattern", sorted(VALID))  # type: ignore[untyped-decorator]
def test_price_scale_and_translation_invariance(pattern: str) -> None:
    source = VALID[pattern]
    original = assess_harmonic(points(source), pattern)
    for scale, translation in ((4.0, 0.0), (0.5, 1000.0), (1.0, -12.0)):
        shifted = tuple(scale * price + translation for price in source)
        other = assess_harmonic(points(shifted), pattern)
        assert other.accepted == original.accepted, (pattern, shifted)
        assert other.direction == 1
        assert other.ratios["CD/BC"] == pytest.approx(original.ratios["CD/BC"])


@pytest.mark.parametrize("pattern", sorted(VALID))  # type: ignore[untyped-decorator]
def test_reversal_zone_available_before_d_but_never_confirms_signal(pattern: str) -> None:
    source = VALID[pattern]
    zone = projected_reversal_zone(points(source[:4]), pattern)
    assert zone is not None
    assert zone[0] < zone[1]
    assert zone[0] <= source[4] <= zone[1]
    assert harmonic_xabcd(points(source[:4]), pattern) == 0


@pytest.mark.parametrize("pattern", sorted(VALID))  # type: ignore[untyped-decorator]
def test_no_future_signal_backfill_in_complete_bar_series(pattern: str) -> None:
    source = VALID[pattern]
    # Repeated plateaus around extrema ensure right-side confirmation is necessary.
    values = [source[0]] * 6
    for x in source[1:]:
        values += [x] * 5
    values += [source[-1]] * 8
    candles = {
        "high": tuple(x + 0.01 for x in values),
        "low": tuple(x - 0.01 for x in values),
        "close": tuple(values),
    }
    full = calculate_chart_pattern(candles, pattern)
    for cutoff in (8, 12, 18, 24, len(values) - 1):
        prefix = {key: v[:cutoff] for key, v in candles.items()}
        assert full[:cutoff] == calculate_chart_pattern(prefix, pattern)
    assert all(x in (-1.0, 0.0, 1.0) for x in full)


def test_boundary_invalid_non_finite_and_same_direction() -> None:
    p = points(VALID["harmonic_gartley"])
    assert not assess_harmonic(p[:-1], "harmonic_gartley").accepted
    assert not assess_harmonic(
        [*p[:4], ConfirmedPivot(4, math.nan, "low", 6)], "harmonic_gartley"
    ).accepted
    with pytest.raises(ValueError):
        assess_harmonic(p, "arbitrary_unvalidated_pattern")


def interpolate_ohlc(
    source: tuple[float, ...],
) -> dict[str, tuple[float, ...]]:
    """Piecewise-linear 5-extrema path with uniquely confirmed close pivots."""
    up = 1 if source[1] > source[0] else -1
    by_index = {
        0: source[0] + 4 * up,
        4: source[0],
        9: source[1],
        14: source[2],
        19: source[3],
        24: source[4],
        29: source[4] + 3 * up,
    }
    timeline: list[float] = []
    ticks = list(by_index)
    for first, last in zip(ticks[:-1], ticks[1:], strict=False):
        timeline.extend(
            by_index[first] + (by_index[last] - by_index[first]) * (t - first) / (last - first)
            for t in range(first, last)
        )
    timeline.append(by_index[29])
    # One-price OHLC bars avoid high/low offsets changing borderline ratios.
    return {key: tuple(timeline) for key in ("high", "low", "close")}


@pytest.mark.parametrize("pattern", sorted(VALID))  # type: ignore[untyped-decorator]
@pytest.mark.parametrize("bearish", (False, True))  # type: ignore[untyped-decorator]
def test_confirmed_harmonic_detects_at_d_known_at_not_before(pattern: str, bearish: bool) -> None:
    sample: tuple[float, ...] = VALID[pattern]
    if bearish:
        sample = tuple(220 - value for value in sample)
    candles = interpolate_ohlc(sample)
    signals = calculate_chart_pattern(candles, pattern)
    assert signals[26] == (-1.0 if bearish else 1.0)
    assert sum(x != 0.0 for x in signals) == 1
    assert all(v == 0.0 for v in signals[:26])
    for cut in range(21, len(signals) + 1):
        prefix = {k: v[:cut] for k, v in candles.items()}
        assert calculate_chart_pattern(prefix, pattern) == signals[:cut]


@pytest.mark.parametrize("pattern", sorted(INVALID))  # type: ignore[untyped-decorator]
def test_invalid_harmonic_never_emits_from_assembled_price_path(pattern: str) -> None:
    candles = interpolate_ohlc(INVALID[pattern])
    signals = calculate_chart_pattern(candles, pattern)
    assert all(signal == 0.0 for signal in signals), (pattern, signals)


def test_legacy_custom_tolerance_cannot_silently_change_rules() -> None:
    with pytest.raises(ValueError):
        harmonic_xabcd(points(VALID["harmonic_gartley"]), "harmonic_gartley", tolerance=0.4)


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    ("pattern", "prices"),
    [
        ("harmonic_gartley", (100.0, 120.0, 107.64, 113.202, 104.28)),
        ("harmonic_butterfly", (100.0, 120.0, 104.28, 117.642, 94.6)),
        ("harmonic_bat", (100.0, 120.0, 112.36, 119.12904, 102.28)),
    ],
)
def test_abcd_ratio_is_an_independent_rule_not_only_a_bc_projection(
    pattern: str, prices: tuple[float, ...]
) -> None:
    outcome = assess_harmonic(points(prices), pattern)
    assert not outcome.accepted
    assert "CD/AB" in outcome.failed_rules, (pattern, outcome)
    assert "CD/BC" not in outcome.failed_rules, (pattern, outcome)


def test_prz_xa_anchor_rejection_even_if_other_ratio_is_close() -> None:
    sample = (100.0, 120.0, 107.64, 116.6, 105.6)
    outcome = assess_harmonic(points(sample), "harmonic_gartley")
    assert not outcome.accepted
    assert "PRZ" in outcome.failed_rules
    assert "CD/BC" not in outcome.failed_rules
