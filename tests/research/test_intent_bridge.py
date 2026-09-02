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
