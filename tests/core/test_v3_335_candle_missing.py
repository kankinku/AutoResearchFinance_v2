"""Regression for 11 native candle patterns on missing OHLCV observations."""

from __future__ import annotations

import math

import pytest

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from scripts.v3_audit_335_features import AVAILABLE, synthetic

PATTERNS = (
    "doji",
    "engulfing",
    "evening_star",
    "fractal",
    "hammer",
    "higher_high_lower_low",
    "inside_bar",
    "morning_star",
    "outside_bar",
    "pin_bar",
    "shooting_star",
)


@pytest.mark.parametrize("name", PATTERNS)
def test_native_candle_pattern_handles_missing_current_and_prior_bars(name: str) -> None:
    source, _ = synthetic(120)
    spec = next(s for s in research_feature_specs() if s.name == name)
    assert set(spec.inputs) <= AVAILABLE
    with_gap = {
        key: tuple(None if i == 45 else value for i, value in enumerate(source[key]))
        for key in spec.inputs
    }
    output = calculate_feature(spec, with_gap)
    shortened = calculate_feature(spec, {key: v[:-1] for key, v in with_gap.items()})
    assert len(output) == 120
    assert output[:-1] == shortened
    assert output[45] is None
    assert all(x is None or math.isfinite(x) for x in output)
