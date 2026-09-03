from __future__ import annotations

import pytest
from pydantic import ValidationError

from strategy_ir.schema import Condition, StrategyIR


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


def test_strategy_ir_accepts_optional_external_features_and_strategy_risk_policy() -> None:
    document = example_document()
    strategy_document = dict(document["strategy"])  # type: ignore[arg-type]
    strategy_document["features"] = {
        "vix_regime": {"feature_id": "vix_percentile", "timeframe": "1d", "lag_bars": 0}
    }
    strategy_document["entry"] = {
        "logic": "AND",
        "conditions": [
            {"op": "greater_than", "left": "vix_regime", "value": 0.8},
        ],
    }
    strategy_document["risk"] = {
        "stop_loss_pct": 4.0,
        "take_profit_pct": 12.0,
        "risk_appetite": 0.35,
        "loss_tolerance_pct": 2.0,
        "daily_loss_limit_pct": 1.5,
        "daily_loss_action": "reduce",
        "max_concurrent_positions": 4,
        "max_total_exposure_pct": 80.0,
    }
    document["strategy"] = strategy_document

    strategy = StrategyIR.model_validate(document)

    assert strategy.features["vix_regime"].feature_id == "vix_percentile"
    assert strategy.risk.daily_loss_action == "reduce"
    assert strategy.risk.max_concurrent_positions == 4


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


def test_condition_normalizes_verified_operator_alias() -> None:
    condition = Condition.model_validate(
        {"op": "gt", "left": "rsi", "value": 70}
    )

    assert condition.op == "greater_than"


def test_condition_rejects_unregistered_operator() -> None:
    with pytest.raises(ValidationError):
        Condition.model_validate(
            {"op": "approximately", "left": "rsi", "value": 70}
        )


def test_indicator_type_normalizes_a_verified_type_name() -> None:
    document = example_document()
    strategy_document = dict(document["strategy"])  # type: ignore[arg-type]
    strategy_document["indicators"] = {"fast": {"type": "ema", "period": 12}}
    document["strategy"] = strategy_document
    strategy = StrategyIR.model_validate(document)

    assert strategy.indicators["fast"].type == "EMA"


def test_indicator_type_rejects_an_unverified_type_name() -> None:
    invalid = example_document()
    invalid_strategy = dict(invalid["strategy"])  # type: ignore[arg-type]
    invalid_strategy["indicators"] = {"fast": {"type": "not_a_real_indicator"}}
    invalid["strategy"] = invalid_strategy

    with pytest.raises(ValidationError):
        StrategyIR.model_validate(invalid)


def test_indicator_type_normalizes_legacy_verified_alias() -> None:
    document = example_document()
    strategy_document = dict(document["strategy"])  # type: ignore[arg-type]
    strategy_document["indicators"] = {"high": {"type": "highest", "period": 20}}
    document["strategy"] = strategy_document

    strategy = StrategyIR.model_validate(document)

    assert strategy.indicators["high"].type == "MAXIMUM"
