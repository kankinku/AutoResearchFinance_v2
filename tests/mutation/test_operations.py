from __future__ import annotations

import pytest

from mutation.engine import MutationError, MutationOperation, apply_operations
from strategy_ir.schema import FeatureRef
from strategy_ir.validator import validate_strategy
from tests.strategy_ir.test_schema import example_document


def strategy():
    return validate_strategy(example_document())


def test_parameter_rule_and_boolean_operations_do_not_mutate_parent() -> None:
    parent = strategy()
    child = apply_operations(
        parent,
        [
            MutationOperation("SET_PARAMETER", "risk.stop_loss_pct", 3.0),
            MutationOperation(
                "ADD_RULE",
                "entry.conditions",
                {"op": "greater_than", "left": "rsi", "value": 20},
            ),
            MutationOperation("CHANGE_AND_OR", "entry.logic", "OR"),
            MutationOperation("DISABLE_RULE", "entry.conditions.0"),
        ],
    )

    assert child.risk.stop_loss_pct == 3.0
    assert len(child.entry.conditions) == 3
    assert child.entry.logic == "OR"
    assert child.entry.conditions[0].enabled is False
    assert parent.risk.stop_loss_pct == 4.0
    assert len(parent.entry.conditions) == 2
    assert parent.entry.conditions[0].enabled is True


def test_structural_and_risk_operations_are_supported() -> None:
    parent = strategy()
    child = apply_operations(
        parent,
        [
            MutationOperation("ADD_INDICATOR", "indicators.adx", {"type": "ADX", "period": 14}),
            MutationOperation(
                "REPLACE_RULE",
                "entry.conditions.1",
                {"op": "greater_than", "left": "rsi", "value": 40},
            ),
            MutationOperation("CHANGE_TAKE_PROFIT", "risk.take_profit_pct", 15.0),
            MutationOperation("CHANGE_TRAILING_STOP", "risk.trailing_stop_pct", 2.0),
            MutationOperation("CHANGE_POSITION_SIZE", "risk.position_size_pct", 50.0),
            MutationOperation(
                "ADD_REGIME_FILTER",
                "regime_filters",
                {"op": "greater_than", "left": "adx", "value": 20},
            ),
        ],
    )

    assert child.indicators["adx"].type == "ADX"
    assert child.entry.conditions[1].value == 40
    assert child.risk.take_profit_pct == 15.0
    assert child.risk.trailing_stop_pct == 2.0
    assert child.risk.position_size_pct == 50.0
    assert len(child.regime_filters) == 1

    removed = apply_operations(
        child, [MutationOperation("REMOVE_REGIME_FILTER", "regime_filters.0")]
    )
    assert removed.regime_filters == []


def test_add_feature_operation_preserves_series_timeframe_and_parameters() -> None:
    parent = strategy()
    child = apply_operations(
        parent,
        [
            MutationOperation(
                "ADD_FEATURE",
                "features.us10y_weekly_rsi",
                FeatureRef(
                    feature_id="rsi",
                    inputs=("US10Y.close",),
                    timeframe="1w",
                    lag_bars=1,
                    parameters={"period": 14},
                ),
            )
        ],
    )

    assert child.features["us10y_weekly_rsi"].feature_id == "rsi"
    assert child.features["us10y_weekly_rsi"].inputs == ("US10Y.close",)
    assert child.features["us10y_weekly_rsi"].timeframe == "1w"
    assert child.features["us10y_weekly_rsi"].parameters == {"period": 14}


def test_remove_swap_replace_entry_exit_and_regime_operations() -> None:
    parent = strategy()
    child = apply_operations(
        parent,
        [
            MutationOperation("REMOVE_RULE", "exit.conditions.1"),
            MutationOperation("SWAP_INDICATOR", "indicators.fast.type", "SMA"),
            MutationOperation("REMOVE_INDICATOR", "indicators.rsi"),
            MutationOperation(
                "CHANGE_ENTRY",
                "entry",
                {
                    "logic": "AND",
                    "conditions": [{"op": "cross_above", "left": "fast", "right": "slow"}],
                },
            ),
            MutationOperation(
                "CHANGE_EXIT",
                "exit",
                {
                    "logic": "OR",
                    "conditions": [{"op": "cross_below", "left": "fast", "right": "slow"}],
                },
            ),
        ],
    )

    assert child.indicators["fast"].type == "SMA"
    assert "rsi" not in child.indicators
    assert len(child.exit.conditions) == 1


def test_crossover_uses_one_parent_entry_and_the_other_exit() -> None:
    left = strategy()
    right_document = example_document()
    right_document["strategy"] = {**right_document["strategy"], "id": "S2", "family": "breakout"}  # type: ignore[arg-type]
    right = validate_strategy(right_document)

    crossed = apply_operations(left, [MutationOperation("CROSSOVER", other=right)])
    combined = apply_operations(left, [MutationOperation("COMBINE_STRATEGY", other=right)])

    assert crossed.entry == left.entry
    assert crossed.exit == right.exit
    assert len(combined.entry.conditions) == len(left.entry.conditions) + len(
        right.entry.conditions
    )
    assert combined.family == left.family


def test_invalid_operation_or_path_is_rejected() -> None:
    with pytest.raises(MutationError, match="unsupported operation"):
        apply_operations(strategy(), [MutationOperation("NOPE")])
    with pytest.raises(MutationError, match="path"):
        apply_operations(strategy(), [MutationOperation("SET_PARAMETER", "risk.unknown", 1)])
