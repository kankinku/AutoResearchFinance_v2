from __future__ import annotations

import pytest

from mutation.primitive_registry import PrimitiveRegistry, UnknownPrimitiveError, default_registry


def test_default_registry_contains_all_architecture_primitives() -> None:
    registry = default_registry()

    assert set(registry.names()) == {
        "sma_cross",
        "ema_cross",
        "rsi",
        "macd",
        "atr",
        "adx",
        "bollinger",
        "volume_breakout",
        "52_week_high",
        "volatility_filter",
        "regime_filter",
        "stop_logic",
        "take_profit",
        "trailing_stop",
        "position_sizing",
    }


def test_registry_rejects_duplicates_and_unknown_lookup() -> None:
    registry = PrimitiveRegistry()
    registry.register("rsi", input_names=("period",), output_type="indicator")
    with pytest.raises(ValueError, match="already registered"):
        registry.register("rsi", input_names=("period",), output_type="indicator")
    with pytest.raises(UnknownPrimitiveError, match="unknown primitive"):
        registry.get("missing")
