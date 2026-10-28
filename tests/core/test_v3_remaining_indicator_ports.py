"""Four-source backlog: independent outputs must stay finite, causal and linked."""

from __future__ import annotations

import math

import pytest

from core.features.calculators import calculate_feature
from core.features.catalog import imported_feature_catalog
from core.features.registry import research_feature_specs
from core.features.source_remaining import DEFINITIONS, NAMES
from tests.core.test_v3_source_multibackend import series


def test_remaining_unique_features_registered_with_licenses() -> None:
    specs = {s.name: s for s in research_feature_specs()}
    assert NAMES <= specs.keys()
    assert len(NAMES) == 13
    for feature, _, inputs, period, license_name in DEFINITIONS:
        s = specs[feature]
        assert s.calculator == "verified_remaining_formula"
        assert s.inputs == inputs
        assert s.lookback == period
        assert s.source_licenses == (license_name,)
        assert s.status == "REGISTERED"


@pytest.mark.parametrize("name", sorted(NAMES))
def test_remaining_each_feature_causal_and_finite(name: str) -> None:
    spec = imported_feature_catalog().resolve(name)
    data = series(210)
    full = calculate_feature(spec, data)
    truncated = calculate_feature(spec, {k: v[:-1] for k, v in data.items()})
    assert len(full) == 210
    assert full[:-1] == truncated, name
    assert any(x is not None for x in full), name
    assert all(x is None or math.isfinite(x) for x in full), name


def test_ibs_flat_and_exact_vectors() -> None:
    spec = imported_feature_catalog().resolve("talib_ibs")
    data = {"high": (12.0, 12.0, 2.0), "low": (8.0, 12.0, 0.0), "close": (10.0, 12.0, 1.0)}
    assert calculate_feature(spec, data) == (0.5, 0.5, 0.5)


def test_fractal_confirmation_never_backpaints() -> None:
    spec = imported_feature_catalog().resolve("stock_fcb_upper")
    highs = (2.0, 3.0, 8.0, 3.0, 2.0, 4.0, 3.0)
    data = {"high": highs, "low": tuple(x - 1 for x in highs)}
    got = calculate_feature(spec, data)
    assert got[:4] == (None,) * 4
    assert got[4] == 8.0


def test_unknown_spec_fails_closed() -> None:
    spec = imported_feature_catalog().resolve("stock_pmo")
    with pytest.raises(ValueError):
        calculate_feature(spec.model_copy(update={"lookback": 1}), {"close": (1.0, 2.0, 3.0)})


def test_talib_swing_index_c_default_limit_move_three() -> None:
    dataset = {
        "open": (100.0, 100.0),
        "high": (101.0, 110.0),
        "low": (99.0, 90.0),
        "close": (100.0, 105.0),
    }
    catalog = imported_feature_catalog()
    expected = 50 * ((5 + 0.5 * 5) / 20) * (10 / 3)
    assert calculate_feature(catalog.resolve("talib_si"), dataset)[1] == pytest.approx(expected)
    assert calculate_feature(catalog.resolve("talib_asi"), dataset)[1] == pytest.approx(expected)
