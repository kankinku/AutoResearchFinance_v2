"""Evidence-backed repairs for the 335-feature catalog's broken EMA chains."""

from __future__ import annotations

import math

import pytest

from core.features.calculators import _ema, _wilder, calculate_feature
from core.features.registry import research_feature_specs
from scripts.v3_audit_335_features import synthetic

BROKEN_BEFORE_FIX = (
    "dema",
    "klinger",
    "macd_histogram",
    "macd_signal",
    "mass_index",
    "rsi.ema",
    "rsi.wilder",
    "rsx",
    "tema",
    "trix",
    "tsi",
    "zero_lag_ema",
)


@pytest.mark.parametrize("name", BROKEN_BEFORE_FIX)
def test_all_priorly_broken_chained_indicators_now_compute(name: str) -> None:
    data, _ = synthetic()
    spec = next(s for s in research_feature_specs() if s.name == name)
    vals = calculate_feature(spec, {key: data[key] for key in spec.inputs})
    earlier = calculate_feature(spec, {key: data[key][:-1] for key in spec.inputs})
    assert vals[:-1] == earlier
    assert any(x is not None and math.isfinite(x) for x in vals)


def test_ema_handles_delayed_start_without_inventing_early_history() -> None:
    series = (None, None, 2.0, 4.0, 8.0, 16.0, 32.0)
    values = _ema(series, 3)
    assert values[:4] == (None, None, None, None)
    assert values[4] == pytest.approx(14 / 3)
    assert values[5] == pytest.approx((14 / 3) * 0.5 + 16 * 0.5)
    assert values[6] == pytest.approx(values[5] * 0.5 + 32 * 0.5)


def test_wilder_handles_delayed_start() -> None:
    data = (None, 3.0, 6.0, 12.0, 15.0, 21.0)
    values = _wilder(data, 3)
    assert values[:3] == (None, None, None)
    assert values[3] == pytest.approx(7.0)
    assert values[4] == pytest.approx((7.0 * 2 + 15) / 3)


def test_ema_missing_gap_requires_full_reseed() -> None:
    observed = _ema((1.0, 2.0, 3.0, None, 10.0, 12.0, 14.0, 16.0), 3)
    assert observed[:6] == (None, None, 2.0, None, None, None)
    assert observed[6] == pytest.approx(12.0)
    assert observed[7] == pytest.approx(14.0)


def test_zero_lag_ema_is_ema_of_causal_de_lagged_close() -> None:
    data = {"close": (1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 13.0)}
    spec = next(s for s in research_feature_specs() if s.name == "zero_lag_ema")
    override = spec.model_copy(update={"lookback": 3})
    output = calculate_feature(override, data)
    assert output[2] is None
    # lag=1: corrected close 2*P[t]-P[t-1] = 5,7,9..., 3-bar SMA seeds at index 3.
    assert output[3] == pytest.approx(7.0)
