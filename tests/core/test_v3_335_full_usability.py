"""Prevent silent loss of claimed Quant V3 scalar research capability."""

from __future__ import annotations

import math

from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from research.llm.inherited_feature_compiler import _new_feature_vector
from scripts.v3_audit_335_features import AVAILABLE, synthetic
from strategy_ir.schema import FeatureRef


def test_every_ohlcv_scalar_has_executable_inherited_replay() -> None:
    source, market = synthetic()
    specs = research_feature_specs()
    assert len(specs) == 447  # 435 legacy + 12 causal chart patterns
    eligible = [
        spec for spec in specs if spec.data_contract == "scalar" and set(spec.inputs) <= AVAILABLE
    ]
    withheld = [spec for spec in specs if spec not in eligible]
    assert len(eligible) == 421  # 409 legacy + 12 chart patterns
    assert len(withheld) == 26
    for spec in eligible:
        inputs = {key: source[key] for key in spec.inputs}
        values = calculate_feature(spec, inputs)
        earlier = calculate_feature(spec, {key: v[:-1] for key, v in inputs.items()})
        ref = FeatureRef(feature_id=spec.name, lookback=spec.lookback, inputs=spec.inputs)
        inherited = _new_feature_vector(ref, market)
        assert len(values) == len(source["close"]), spec.name
        assert values[:-1] == earlier, spec.name
        assert inherited == values, spec.name
        assert any(v is not None for v in values), spec.name
        assert all(v is None or math.isfinite(v) for v in values), spec.name
