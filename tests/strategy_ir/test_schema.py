from __future__ import annotations

import pytest
from pydantic import ValidationError

from strategy_ir.schema import StrategyIR


def example_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "strategy": {
            "id": "S001923",
            "family": "momentum",
            "generation": 28,
            "parents": ["momentum_014", "volatility_009"],
            "indicators": {
                "fast": {"type": "EMA", "period": 12},
                "slow": {"type": "EMA", "period": 40},
                "rsi": {"type": "RSI", "period": 14},
            },
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"op": "cross_above", "left": "fast", "right": "slow"},
                    {"op": "less_than", "left": "rsi", "value": 38},
                ],
            },
            "exit": {
                "logic": "OR",
                "conditions": [
                    {"op": "cross_below", "left": "fast", "right": "slow"},
                    {"op": "greater_than", "left": "rsi", "value": 72},
                ],
            },
            "risk": {"stop_loss_pct": 4.0, "take_profit_pct": 12.0},
            "research": {"mutation": ["M193", "M228"], "parent_score": 0.712},
        },
    }


def test_strategy_ir_parses_architecture_shape() -> None:
    strategy = StrategyIR.model_validate(example_document())

    assert strategy.strategy_id == "S001923"
    assert strategy.family == "momentum"
    assert strategy.indicators["fast"].type == "EMA"
    assert strategy.entry.conditions[1].value == 38
    assert strategy.risk.trailing_stop_pct is None


def test_strategy_ir_rejects_unknown_fields_and_invalid_period() -> None:
    document = example_document()
    document["strategy"] = {**document["strategy"], "unexpected": True}  # type: ignore[dict-item]
    with pytest.raises(ValidationError):
        StrategyIR.model_validate(document)

    invalid = example_document()
    invalid_strategy = dict(invalid["strategy"])  # type: ignore[arg-type]
    invalid_strategy["indicators"] = {"fast": {"type": "EMA", "period": 0}}
    invalid["strategy"] = invalid_strategy
    with pytest.raises(ValidationError):
        StrategyIR.model_validate(invalid)
