"""These V3 ports must feed the actual inherited StrategyIR feature binder."""
from __future__ import annotations

from core.features.catalog import imported_feature_catalog
from research.llm.inherited_feature_compiler import _new_feature_vector
from strategy_ir.schema import FeatureRef
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture


def test_source_ports_reach_strategy_ir_compiler() -> None:
    _, market = _warmup_fixture()
    for name in ("balance_of_power", "harami", "spinning_top"):
        spec = imported_feature_catalog().resolve(name)
        feature = FeatureRef(
            feature_id=name, timeframe="1d",
            lookback=min(2, spec.lookback), inputs=spec.inputs,
        )
        vector = _new_feature_vector(feature, market)
        assert len(vector) == len(market.bars)
        assert all(v is None or isinstance(v, float) for v in vector)
