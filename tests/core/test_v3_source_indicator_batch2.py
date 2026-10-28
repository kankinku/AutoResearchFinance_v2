"""Second non-duplicate V3 source-derived candidate batch, independent math & prefix tests."""

from __future__ import annotations

import math

import pytest

from core.features.calculators import calculate_feature
from core.features.catalog import imported_feature_catalog
from core.features.registry import research_feature_specs
from research.llm.inherited_feature_compiler import _new_feature_vector
from strategy_ir.schema import FeatureRef
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture

NUMERIC = {
    "bias_ratio": ("close",),
    "chande_forecast_oscillator": ("close",),
    "absolute_price_oscillator": ("close",),
    "percentage_price_oscillator": ("close",),
    "psychological_line": ("close",),
    "kdj_j": ("high", "low", "close"),
    "brar_ar": ("open", "high", "low"),
    "brar_br": ("high", "low", "close"),
    "ttm_trend": ("high", "low", "close"),
    "acceleration_band_upper": ("high", "low", "close"),
    "market_facilitation_index": ("high", "low", "volume"),
    "williams_ad": ("high", "low", "close"),
    "price_volume_rank": ("close", "volume"),
    "thermometer": ("high", "low"),
    "pretty_good_oscillator": ("high", "low", "close"),
}
PATTERNS = (
    "hanging_man",
    "inverted_hammer",
    "belt_hold",
    "harami_cross",
    "matching_low",
    "high_wave",
    "long_legged_doji",
    "three_inside",
)


def bars(n: int = 150) -> dict[str, tuple[float, ...]]:
    close = tuple(100 + 0.16 * i + math.sin(i / 4) * 2.0 for i in range(n))
    opening = tuple(v + (0.4 if i % 2 else -0.3) for i, v in enumerate(close))
    return {
        "open": opening,
        "high": tuple(max(a, b) + 1.2 for a, b in zip(opening, close, strict=True)),
        "low": tuple(min(a, b) - 1.0 for a, b in zip(opening, close, strict=True)),
        "close": close,
        "volume": tuple(400 + 7 * (i % 13) for i in range(n)),
    }


def test_catalog_batch2_fully_registered_with_mit_provenance() -> None:
    specs = {s.name: s for s in research_feature_specs()}
    assert len(specs) >= 214  # future source batches preserve this cohort
    for name in (*NUMERIC, *PATTERNS):
        assert name in specs, name
        spec = specs[name]
        assert spec.status == "REGISTERED"
        assert spec.source_licenses == ("MIT",)
        assert "pandas-ta-classic@" in spec.source_repositories[0]
        assert spec.data_contract == "scalar"
        assert spec.calculator == name
    assert not imported_feature_catalog().duplicates()


@pytest.mark.parametrize("name", list(NUMERIC) + list(PATTERNS))
def test_batch2_past_only_repeatable_and_finite(name: str) -> None:
    s = imported_feature_catalog().resolve(name)
    data = bars()
    full = calculate_feature(s, data)
    earlier = calculate_feature(s, {key: values[:-1] for key, values in data.items()})
    assert len(full) == len(data["close"])
    assert len(earlier) == len(data["close"]) - 1
    assert full[:-1] == earlier, name
    assert all(v is None or math.isfinite(v) for v in full)
    assert any(v is not None for v in full)
    assert full == calculate_feature(s, data)
    assert full[: s.lookback - 1] == (None,) * (s.lookback - 1)


@pytest.mark.parametrize("name", list(NUMERIC) + list(PATTERNS))
def test_batch2_missing_and_flat_handled_without_explosive_values(name: str) -> None:
    s = imported_feature_catalog().resolve(name)
    flat = {
        key: (100.0,) * 70 if key != "volume" else (1000.0,) * 70
        for key in ("open", "high", "low", "close", "volume")
    }
    got = calculate_feature(s, flat)
    assert all(v is None or math.isfinite(v) for v in got)
    damaged = dict(flat)
    damaged[s.inputs[0]] = (None,) + damaged[s.inputs[0]][1:]
    got2 = calculate_feature(s, damaged)
    assert all(v is None or math.isfinite(v) for v in got2)


def test_analytical_vectors() -> None:
    catalog = imported_feature_catalog()
    prices = {"close": (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)}
    bias = catalog.resolve("bias_ratio").model_copy(update={"lookback": 3})
    assert calculate_feature(bias, prices)[-1] == pytest.approx(6 / 5 - 1)
    psl = catalog.resolve("psychological_line").model_copy(update={"lookback": 3})
    assert calculate_feature(psl, prices)[3:] == (100.0, 100.0, 100.0)
    apo = catalog.resolve("absolute_price_oscillator").model_copy(
        update={"lookback": 3, "parameters": {"fast": 2}}
    )
    assert calculate_feature(apo, prices)[-1] == pytest.approx(0.5)
    ppo = catalog.resolve("percentage_price_oscillator").model_copy(
        update={"lookback": 3, "parameters": {"fast": 2}}
    )
    assert calculate_feature(ppo, prices)[-1] == pytest.approx(10.0)
    data = {
        "high": (10.0, 12.0, 15.0, 17.0),
        "low": (7.0, 9.0, 11.0, 13.0),
        "volume": (3.0, 2.0, 5.0, 4.0),
        "close": (8.0, 11.0, 14.0, 16.0),
        "open": (9.0, 10.0, 12.0, 14.0),
    }
    mfi = catalog.resolve("market_facilitation_index")
    assert calculate_feature(mfi, data)[-1] == pytest.approx(1.0)
    rank = catalog.resolve("price_volume_rank")
    assert calculate_feature(rank, data)[1:] == (2.0, 1.0, 2.0)


def test_second_batch_independent_strategy_ir_feature_binding() -> None:
    _, market = _warmup_fixture()
    for name in ("bias_ratio", "market_facilitation_index", "hanging_man"):
        spec = imported_feature_catalog().resolve(name)
        ref = FeatureRef(feature_id=name, lookback=2, inputs=spec.inputs)
        got = _new_feature_vector(ref, market)
        assert len(got) == len(market.bars)


def test_signed_candle_scenarios() -> None:
    catalog = imported_feature_catalog()
    # Dark initial body, then a narrow inside doji: bullish harami cross.
    data = {
        "open": (20.0, 12.0, 10.0, 14.0),
        "high": (21.0, 14.0, 17.0, 15.0),
        "low": (9.0, 11.0, 9.9, 13.0),
        "close": (10.0, 12.01, 10.5, 13.1),
        "volume": (100.0,) * 4,
    }
    assert calculate_feature(catalog.resolve("harami_cross"), data)[1] == 1.0
    assert calculate_feature(catalog.resolve("inverted_hammer"), data)[2] == 1.0
