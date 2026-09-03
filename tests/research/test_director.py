from __future__ import annotations

import pytest

from research.llm.director import IntentOperation, ResearchDirector, ResearchIntent
from research.llm.provider import OfflineProvider


def test_offline_director_returns_deterministic_intent_without_code_patch() -> None:
    director = ResearchDirector(OfflineProvider())
    context = {"generation": 4, "frontier": ["S1"], "unexplored": ["volatility"]}

    first = director.propose(context)
    second = director.propose(context)

    assert first == second
    assert isinstance(first, ResearchIntent)
    assert first.parent_ids == ("S1",)
    assert first.python_patch is None
    assert first.evaluator_change is None


def test_offline_director_selects_a_catalog_feature_as_structured_proposal() -> None:
    intent = ResearchDirector(OfflineProvider()).propose(
        {
            "frontier": ["S1"],
            "feature_catalog": [
                {
                    "name": "vix_percentile",
                    "family": "macro",
                    "inputs": ["VIX.close"],
                    "calculator": "percentile",
                    "lookback": 20,
                }
            ],
        }
    )

    assert intent.feature_proposal is not None
    assert intent.feature_proposal.name == "vix_percentile"
    assert intent.python_patch is None


def test_director_rejects_forbidden_intent_fields() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        ResearchIntent(
            mode="structure",
            parent_ids=("S1",),
            operations=(),
            rationale="bad",
            python_patch="write evaluator",
        )


def test_director_can_request_an_independent_repair() -> None:
    class RepairProvider(OfflineProvider):
        def repair(
            self,
            context: dict[str, object],
            invalid_intent: dict[str, object] | None,
            error: str,
        ) -> dict[str, object]:
            assert context == {"generation": 1}
            assert invalid_intent == {"mode": "mixed"}
            assert error == "invalid"
            return {
                "mode": "structure",
                "parent_ids": ["S1"],
                "operations": [],
                "rationale": "repaired",
            }

    intent = ResearchDirector(RepairProvider()).repair(
        {"generation": 1}, {"mode": "mixed"}, "invalid"
    )

    assert intent.rationale == "repaired"


def test_canonical_regime_filter_operation_requires_a_condition_object() -> None:
    operation = IntentOperation(
        op="ADD_REGIME_FILTER",
        path="regime_filters",
        condition={"op": "greater_than", "left": "VIX.close", "value": 25},
    )

    assert operation.condition is not None
    assert operation.condition.left == "VIX.close"

    with pytest.raises(ValueError, match="condition"):
        IntentOperation(
            op="ADD_REGIME_FILTER",
            path="regime_filters",
            condition=True,
        )


def test_canonical_indicator_operation_requires_an_indicator_object() -> None:
    operation = IntentOperation(
        op="ADD_INDICATOR",
        path="indicators.fast_ema",
        indicator={"type": "EMA", "period": 5, "parameters": {}},
    )

    assert operation.indicator is not None
    assert operation.indicator.type == "EMA"

    with pytest.raises(ValueError, match="indicator"):
        IntentOperation(op="ADD_INDICATOR", path="indicators.fast_ema", value=True)
