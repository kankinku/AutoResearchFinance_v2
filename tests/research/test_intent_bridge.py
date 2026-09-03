from __future__ import annotations

import pytest

from core.features.registry import research_feature_specs
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import (
    IntentEligibilityError,
    apply_intent,
    intent_to_operations,
)
from strategy_ir.validator import validate_strategy
from tests.strategy_ir.test_schema import example_document


def test_registered_feature_selection_becomes_add_feature_operation() -> None:
    intent = ResearchIntent(
        mode="mixed",
        parent_ids=("QQQ-base",),
        operations=(),
        rationale="use weekly RSI as a regime input",
        feature_selections=(
            {
                "alias": "us10y_weekly_rsi",
                "feature_id": "rsi",
                "inputs": ("US10Y.close",),
                "timeframe": "1w",
                "lag_bars": 1,
                "lookback": 14,
                "parameters": {"period": 14},
            },
        ),
    )

    operations = intent_to_operations(intent, research_feature_specs())

    assert operations[-1].op == "ADD_FEATURE"
    assert operations[-1].path == "features.us10y_weekly_rsi"
    assert operations[-1].value.feature_id == "rsi"
    assert operations[-1].value.timeframe == "1w"
    assert operations[-1].value.lag_bars == 1
    assert operations[-1].value.lookback == 14
    assert operations[-1].value.parameters == {"period": 14}


def test_unregistered_feature_selection_is_not_experiment_eligible() -> None:
    intent = ResearchIntent(
        mode="structure",
        parent_ids=("QQQ-base",),
        rationale="try an unregistered feature",
        feature_selections=(
            {"alias": "unknown", "feature_id": "does_not_exist"},
        ),
    )

    with pytest.raises(IntentEligibilityError, match="not registered"):
        intent_to_operations(intent, research_feature_specs())


def test_primary_ohlcv_inputs_are_valid_feature_inputs() -> None:
    intent = ResearchIntent(
        mode="structure",
        parent_ids=("QQQ-base",),
        rationale="use a daily trend-strength feature",
        feature_selections=(
            {
                "alias": "trend_strength",
                "feature_id": "dmi_adx",
                "inputs": ("high", "low", "close"),
            },
        ),
    )

    operations = intent_to_operations(intent, research_feature_specs())

    assert operations[-1].value.inputs == ("high", "low", "close")


def test_json_patch_intent_operations_are_converted_to_typed_mutations() -> None:
    intent = ResearchIntent(
        mode="mixed",
        parent_ids=("QQQ-base",),
        rationale="use a faster crossover and an entry filter",
        operations=(
            {
                "op": "replace",
                "path": "/source_strategy/indicators/sma_fast/period",
                "value": 3,
            },
            {
                "op": "add",
                "path": "/source_strategy/entry/conditions/-",
                "value": '{"op":"greater_than","left":"close","value":0}',
            },
        ),
    )

    operations = intent_to_operations(intent, research_feature_specs())

    assert operations[0].op == "SET_PARAMETER"
    assert operations[0].path == "indicators.sma_fast.period"
    assert operations[1].op == "ADD_RULE"
    assert operations[1].path == "entry.conditions"
    assert operations[1].value == {"op": "greater_than", "left": "close", "value": 0}


def test_canonical_condition_operations_are_converted_to_condition_values() -> None:
    intent = ResearchIntent(
        mode="mixed",
        parent_ids=("QQQ-base",),
        rationale="add a typed macro regime filter",
        operations=(
            {
                "op": "ADD_REGIME_FILTER",
                "path": "regime_filters",
                "condition": {
                    "op": "less_than",
                    "left": "US10Y.close",
                    "value": 5,
                },
            },
        ),
    )

    operations = intent_to_operations(intent, research_feature_specs())

    assert operations[0].op == "ADD_REGIME_FILTER"
    assert operations[0].path == "regime_filters"
    assert operations[0].value == {
        "op": "less_than",
        "left": "US10Y.close",
        "value": 5,
    }


def test_canonical_indicator_operation_is_converted_to_an_indicator_value() -> None:
    intent = ResearchIntent(
        mode="structure",
        parent_ids=("QQQ-base",),
        rationale="add a fast EMA",
        operations=(
            {
                "op": "ADD_INDICATOR",
                "path": "indicators.fast_ema",
                "indicator": {"type": "EMA", "period": 5, "parameters": {}},
            },
        ),
    )

    operations = intent_to_operations(intent, research_feature_specs())

    assert operations[0].op == "ADD_INDICATOR"
    assert operations[0].value == {"type": "EMA", "period": 5, "parameters": {}}


def test_regime_filter_add_cannot_target_an_item_or_use_a_boolean() -> None:
    for path in ("regime_filters.0",):
        intent = ResearchIntent(
            mode="structure",
            parent_ids=("QQQ-base",),
            rationale="invalid regime filter operation",
            operations=(
                {
                    "op": "ADD_REGIME_FILTER",
                    "path": path,
                    "condition": {"op": "greater_than", "left": "close", "value": 1},
                },
            ),
        )

        with pytest.raises(IntentEligibilityError, match="INTENT_"):
            intent_to_operations(intent, research_feature_specs())

    with pytest.raises(ValueError, match="condition"):
        ResearchIntent(
            mode="structure",
            parent_ids=("QQQ-base",),
            rationale="invalid regime filter value",
            operations=(
                {
                    "op": "ADD_REGIME_FILTER",
                    "path": "regime_filters",
                    "condition": True,
                },
            ),
        )


def test_retain_operation_is_a_safe_noop() -> None:
    intent = ResearchIntent(
        mode="structure",
        parent_ids=("QQQ-base",),
        rationale="retain the parent when no safe mutation is found",
        operations=({"op": "retain"},),
    )

    assert intent_to_operations(intent, research_feature_specs()) == ()


def test_retain_operation_cannot_carry_a_mutation() -> None:
    with pytest.raises(ValueError, match="RETAIN"):
        ResearchIntent(
            mode="structure",
            parent_ids=("QQQ-base",),
            rationale="invalid retain payload",
            operations=({"op": "retain", "path": "risk.stop_loss_pct", "value": 1},),
        )


def test_feature_proposal_does_not_make_feature_eligible_in_same_intent() -> None:
    intent = ResearchIntent(
        mode="structure",
        parent_ids=("QQQ-base",),
        rationale="propose a new feature",
        feature_proposal={
            "name": "new_macro_feature",
            "family": "macro",
            "inputs": ("VIX.close",),
            "calculator": "percentile",
            "lookback": 20,
            "formula": "percentile(VIX.close, 20)",
            "justification": "regime filter",
        },
    )

    with pytest.raises(IntentEligibilityError, match="verification"):
        intent_to_operations(intent, research_feature_specs())


def test_apply_intent_changes_strategy_ir_without_allowing_unregistered_features() -> None:
    parent = validate_strategy(example_document())
    intent = ResearchIntent(
        mode="structure",
        parent_ids=(parent.strategy_id,),
        rationale="add a registered macro feature",
        feature_selections=(
            {
                "alias": "vix_regime",
                "feature_id": "vix_percentile",
                "inputs": ("VIX.close",),
                "timeframe": "1d",
                "lookback": 20,
            },
        ),
    )

    child = apply_intent(parent, intent, research_feature_specs())

    assert child.features["vix_regime"].feature_id == "vix_percentile"
    assert parent.strategy_id in child.parents
    assert child.research.mutation[-1] == "ADD_FEATURE:features.vix_regime"
