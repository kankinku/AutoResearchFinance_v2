from __future__ import annotations

import math

import pytest

from core.features.calculators import calculate_feature
from core.features.catalog import imported_feature_catalog
from core.features.registry import research_feature_specs

NAMES = {
    "talib_adr",
    "talib_rvol",
    "talib_imi",
    "talib_ac",
    "talib_rogers_satchell",
    "stock_elder_bull",
    "stock_elder_bear",
    "stock_starc_upper",
    "stock_starc_lower",
    "stock_alligator_jaw",
    "stock_alligator_teeth",
    "stock_alligator_lips",
}


def series(n: int) -> dict[str, tuple[float, ...]]:
    close = tuple(100 + 0.2 * i + math.sin(i / 4) * 3 for i in range(n))
    opening = tuple(value - (0.4 if i % 2 else -0.3) for i, value in enumerate(close))
    return {
        "open": opening,
        "close": close,
        "high": tuple(max(c, o) + 1 for c, o in zip(close, opening, strict=True)),
        "low": tuple(min(c, o) - 1 for c, o in zip(close, opening, strict=True)),
        "volume": tuple(1000 + 30 * (i % 9) for i in range(n)),
    }


def test_all_additional_c_and_csharp_math_ports_are_attributed() -> None:
    specs = {s.name: s for s in research_feature_specs()}
    assert NAMES <= specs.keys()
    for key in NAMES:
        sp = specs[key]
        assert sp.status == "REGISTERED"
        assert sp.source_licenses in (("BSD-3-Clause",), ("Apache-2.0",))
        assert sp.source_repositories


@pytest.mark.parametrize("name", sorted(NAMES))
def test_all_extra_ports_use_past_only_and_remain_finite(name: str) -> None:
    spec = imported_feature_catalog().resolve(name)
    data = series(155)
    output = calculate_feature(spec, data)
    prefix = calculate_feature(spec, {k: v[:-1] for k, v in data.items()})
    assert output[:-1] == prefix
    assert any(x is not None for x in output)
    assert all(v is None or math.isfinite(v) for v in output)


def test_exact_known_formula_examples() -> None:
    cat = imported_feature_catalog()
    d = {
        "open": (10.0, 10.0, 10.0, 10.0),
        "close": (10.0, 10.0, 10.0, 10.0),
        "high": (12.0, 12.0, 12.0, 12.0),
        "low": (8.0, 8.0, 8.0, 8.0),
        "volume": (10.0, 20.0, 30.0, 40.0),
    }
    adr = cat.resolve("talib_adr").model_copy(update={"lookback": 2})
    assert calculate_feature(adr, d)[1:] == (4.0, 4.0, 4.0)
    rvol = cat.resolve("talib_rvol").model_copy(update={"lookback": 2})
    assert calculate_feature(rvol, d)[2] == pytest.approx(30 / 15)
    assert calculate_feature(rvol, d)[3] == pytest.approx(40 / 25)
    imi = cat.resolve("talib_imi").model_copy(update={"lookback": 2})
    assert calculate_feature(imi, d)[1:] == (50.0, 50.0, 50.0)
    rs = cat.resolve("talib_rogers_satchell").model_copy(update={"lookback": 2})
    assert all(x is not None and x >= 0 for x in calculate_feature(rs, d)[1:])
