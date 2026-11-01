"""A12 regression: effective lagged signals must not be lagged twice by core."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import _feature_values
from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.strategy_adapter import _raw_feature_inputs_for_core
from strategy_ir.schema import StrategyIR


def _fixture() -> tuple[MarketDataSet, StrategyIR]:
    bars = tuple(
        Bar(
            timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            symbol="ZZZ",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=10.0,
        ) for i in range(12)
    )
    market = MarketDataSet(version="a12-causal-bridge", zone=DataZone.DEVELOPMENT, bars=bars)
    strategy = StrategyIR.model_validate({
        "schema_version": 1,
        "id": "a12-lag-provenance",
        "family": "a12_test",
        "generation": 0,
        "indicators": {"unused_sma": {"type": "SMA", "period": 2}},
        "features": {"a": {"feature_id": "synthetic-only", "lag_bars": 3}},
        "entry": {"logic": "AND", "conditions": [
            {"op": "greater_than", "left": "a", "value": 0}
        ]},
        "exit": {"logic": "OR", "conditions": [
            {"op": "less_equal", "left": "a", "value": 0}
        ]},
        "risk": {"stop_loss_pct": 0.0, "take_profit_pct": 0.0},
    })
    return market, strategy


def test_effective_three_bar_delay_applied_once_at_execution_boundary() -> None:
    market, strategy = _fixture()
    effective = (None, None, None, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    supplied = _raw_feature_inputs_for_core(strategy, {"a": effective})
    # The core engine remains unchanged. It must see an unshifted supply vector.
    assert supplied["a"][2] == 1.0
    executed = _feature_values(market, strategy, supplied, None, None)
    assert tuple(executed["a"]) == effective
    assert effective[5] == 1.0 and executed["a"][8] == 0.0


def test_zero_lag_unmodified_and_tampered_prefix_fails_closed() -> None:
    _, strategy = _fixture()
    no_lag = strategy.model_copy(update={
        "features": {"a": strategy.features["a"].model_copy(update={"lag_bars": 0})}
    })
    effective = (None, 1.0, 2.0, 3.0)
    assert _raw_feature_inputs_for_core(no_lag, {"a": effective})["a"] == effective
    with pytest.raises(ValueError, match="lagged.*prefix"):
        _raw_feature_inputs_for_core(strategy, {"a": (1.0, None, None, 2.0)})
