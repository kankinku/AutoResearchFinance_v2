from __future__ import annotations

import math

import pytest

from core.features.calculators import calculate_feature
from core.features.catalog import imported_feature_catalog
from core.features.registry import research_feature_specs

NEW_NUMERIC = {
    "choppiness_index": (("high", "low", "close"), 14),
    "squeeze_on": (("high", "low", "close"), 20),
    "chandelier_exit_long": (("high", "low", "close"), 22),
    "awesome_oscillator": (("high", "low"), 34),
    "kst": (("close",), 30),
    "coppock_curve": (("close",), 14),
    "efficiency_ratio": (("close",), 10),
    "vertical_horizontal_filter": (("close",), 28),
    "correlation_trend_indicator": (("close",), 14),
    "balance_of_power": (("open", "high", "low", "close"), 1),
}
NEW_PATTERNS = (
    "harami",
    "piercing_pattern",
    "dark_cloud_cover",
    "three_white_soldiers",
    "three_black_crows",
    "spinning_top",
    "dragonfly_doji",
    "gravestone_doji",
)


def bars(n: int = 125) -> dict[str, tuple[float, ...]]:
    close = tuple(100.0 + 0.2 * i + 1.5 * math.sin(i / 6) for i in range(n))
    return {
        "open": tuple(x - 0.35 for x in close),
        "high": tuple(x + 1.25 for x in close),
        "low": tuple(x - 1.5 for x in close),
        "close": close,
    }


def test_new_source_features_are_unique_registered_with_attribution() -> None:
    catalog = imported_feature_catalog()
    names = {spec.name for spec in catalog.all()}
    assert len(names) == len(catalog.all())
    assert set(NEW_NUMERIC) | set(NEW_PATTERNS) <= names
    assert set(NEW_NUMERIC) | set(NEW_PATTERNS) <= {
        spec.name for spec in research_feature_specs() if spec.status == "REGISTERED"
    }
    for name in (*NEW_NUMERIC, *NEW_PATTERNS):
        spec = catalog.resolve(name)
        assert spec.source_repositories
        assert spec.source_licenses == ("MIT",)
        assert spec.data_contract == "scalar"


@pytest.mark.parametrize("name,parts", NEW_NUMERIC.items())
def test_new_indicators_are_causal_bounded_and_finite(
    name: str, parts: tuple[tuple[str, ...], int]
) -> None:
    inputs, _ = parts
    spec = imported_feature_catalog().resolve(name)
    data = bars()
    output = calculate_feature(spec, data)
    assert len(output) == len(data["close"])
    assert all(v is None or math.isfinite(v) for v in output)
    assert any(v is not None for v in output)
    assert calculate_feature(spec, {k: v[:-1] for k, v in data.items()}) == output[:-1]
    with pytest.raises(ValueError, match="missing input"):
        calculate_feature(spec, {k: data[k] for k in inputs[:-1]})


def test_formula_known_vectors() -> None:
    catalog = imported_feature_catalog()
    data = bars()
    bop = calculate_feature(catalog.resolve("balance_of_power"), data)
    assert bop[0] == pytest.approx(0.35 / 2.75)

    trending = {"close": (1., 2., 3., 4., 5., 6., 7., 8., 9., 10., 11.)}
    er = catalog.resolve("efficiency_ratio").model_copy(update={"lookback": 3})
    assert calculate_feature(er, trending)[3:] == pytest.approx((1.,) * 8)
    vhf = catalog.resolve("vertical_horizontal_filter").model_copy(update={"lookback": 3})
    assert calculate_feature(vhf, trending)[-1] == pytest.approx(2 / 3)


def test_missing_flat_data_does_not_create_infinite_signal() -> None:
    data = {k: (100.0,) * 80 for k in ("open", "high", "low", "close")}
    for name in NEW_NUMERIC:
        result = calculate_feature(imported_feature_catalog().resolve(name), data)
        assert all(v is None or math.isfinite(v) for v in result), name


def test_candle_patterns_are_historical_signed_values() -> None:
    patterns = imported_feature_catalog()
    source = {
        "open": (20., 12., 10., 22., 10., 11., 12.),
        "high": (21., 14., 21., 23., 12., 13., 14.),
        "low": (9., 11., 9., 12., 9.5, 10.5, 11.5),
        "close": (10., 13., 20., 14., 11.8, 12.8, 13.8),
    }
    for name in NEW_PATTERNS:
        spec = patterns.resolve(name)
        output = calculate_feature(spec, source)
        assert len(output) == 7
        assert all(v is None or v in (-1.0, 0.0, 1.0) for v in output)
        assert calculate_feature(
            spec, {key: values[:-1] for key, values in source.items()}
        ) == output[:-1]
    assert calculate_feature(patterns.resolve("harami"), source)[1] == 1.0
    assert calculate_feature(patterns.resolve("dark_cloud_cover"), source)[3] == -1.0


def test_distinct_candle_shapes() -> None:
    catalog = imported_feature_catalog()
    source = {
        "open": (10.0, 10.0, 20.0, 8.0),
        "high": (10.04, 12.0, 21.0, 17.0),
        "low": (8.0, 9.99, 9.0, 7.0),
        "close": (10.03, 10.01, 10.0, 16.0),
    }
    assert calculate_feature(catalog.resolve("dragonfly_doji"), source)[0] == 1.0
    assert calculate_feature(catalog.resolve("gravestone_doji"), source)[1] == -1.0
    assert calculate_feature(catalog.resolve("piercing_pattern"), source)[-1] == 1.0
