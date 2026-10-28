"""Causal chart pattern rule tests: historical pivot is never traded before confirmation."""
from __future__ import annotations

import math

import pytest

from core.features.chart_patterns import (
    PATTERNS,
    ConfirmedPivot,
    abc_three,
    calculate_chart_pattern,
    complex_correction,
    harmonic_xabcd,
    impulse_five,
)
from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs


def p(values: list[float]) -> list[ConfirmedPivot]:
    return [ConfirmedPivot(i, float(x), "high" if i % 2 else "low", i + 2)
            for i, x in enumerate(values)]


def bars(n: int = 175) -> dict[str, tuple[float, ...]]:
    close = tuple(100 + .08*i + 8*math.sin(i/4) for i in range(n))
    return {"high": tuple(x+1.5 for x in close),
            "low": tuple(x-1.5 for x in close), "close": close}


def test_elliott_five_rules():
    assert impulse_five(p([100, 110, 105, 122, 115, 130])) == 1
    assert impulse_five(p([130, 120, 125, 108, 115, 100])) == -1
    assert impulse_five(p([100, 110, 98, 122, 115, 130])) == 0
    assert impulse_five(p([100, 110, 105, 122, 108, 130])) == 0


def test_abc_and_wxy():
    assert abc_three(p([100, 110, 105, 116])) == 1
    assert abc_three(p([116, 106, 111, 99])) == -1
    wxy = [100, 110, 105, 116, 106, 111, 99, 110, 105, 116]
    assert complex_correction(p(wxy), 3) == 1
    assert complex_correction(p(wxy[:-1]), 3) == 0
    assert complex_correction(p(wxy + [106, 111, 99, 110, 105, 116]), 5) == 1


def test_original_harmonic_ratio_geometry():
    assert harmonic_xabcd(p([100, 120, 104.28, 114, 94.6]), "harmonic_butterfly") == 1
    assert harmonic_xabcd(p([100, 120, 107.64, 115, 104.28]), "harmonic_gartley") == 1
    assert harmonic_xabcd(p([100, 120, 110, 115, 102.28]), "harmonic_bat") == 1
    assert harmonic_xabcd(p([100, 120, 110, 115, 87.64]), "harmonic_crab") == 1
    assert harmonic_xabcd(p([100, 120, 104.28, 114, 94.6]), "harmonic_bat") == 0


@pytest.mark.parametrize("pattern", PATTERNS)
def test_every_pattern_has_registered_inherited_scalar_and_is_prefix_stable(pattern: str):
    spec = next(s for s in research_feature_specs() if s.name == "chart_" + pattern)
    assert spec.status == "REGISTERED"
    assert spec.calculator == "chart_geometry"
    assert spec.data_contract == "scalar"
    data = bars()
    result = calculate_feature(spec, data)
    assert len(result) == len(data["close"])
    assert all(x in (-1., 0., 1.) for x in result)
    for cutoff in (40, 80, 140, 174):
        part = calculate_feature(spec, {k: v[:cutoff] for k, v in data.items()})
        assert result[:cutoff] == part
    assert result == calculate_chart_pattern(
        data, pattern, lookback=spec.lookback,
        confirmation_bars=int(spec.parameters["confirmation_bars"]),
        minimum_swing=float(spec.parameters["minimum_swing"]),
    )


def test_bad_input_and_no_future_backfill():
    data = bars()
    values = {k: list(v) for k, v in data.items()}
    values["close"][76] = None
    signal = calculate_chart_pattern(values, "elliott_abc")
    assert len(signal) == len(data["close"])
    assert all(x in (-1., 0., 1.) for x in signal)
    for cutoff in (80, 120, 174):
        prefix = calculate_chart_pattern(
            {k: v[:cutoff] for k, v in values.items()}, "elliott_abc"
        )
        assert signal[:cutoff] == prefix
    with pytest.raises(ValueError):
        calculate_chart_pattern(data, "unknown_unreviewed_name")
