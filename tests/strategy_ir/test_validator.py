from __future__ import annotations

import pytest

from strategy_ir.validator import StrategyValidationError, validate_strategy
from tests.strategy_ir.test_schema import example_document


def test_validator_accepts_valid_strategy() -> None:
    strategy = validate_strategy(example_document())
    assert strategy.strategy_id == "S001923"


def test_validator_accepts_references_to_declared_external_features() -> None:
    document = example_document()
    strategy = dict(document["strategy"])  # type: ignore[arg-type]
    strategy["features"] = {"vix": {"feature_id": "vix_percentile"}}
    strategy["entry"] = {
        "logic": "AND",
        "conditions": [{"op": "greater_than", "left": "vix", "value": 0.8}],
    }
    document["strategy"] = strategy

    assert validate_strategy(document).features["vix"].feature_id == "vix_percentile"


@pytest.mark.parametrize(
    "change, message",
    [
        (
            {
                "entry": {
                    "logic": "AND",
                    "conditions": [
                        {"op": "cross_above", "left": "missing", "right": "slow"}
                    ],
                }
            },
            "unknown reference",
        ),
        ({"entry": {"logic": "AND", "conditions": []}}, "at least one"),
        (
            {
                "entry": {
                    "logic": "XOR",
                    "conditions": [{"op": "cross_above", "left": "fast", "right": "slow"}],
                }
            },
            "logic",
        ),
    ],
)
def test_validator_rejects_semantically_invalid_strategy(
    change: dict[str, object], message: str
) -> None:
    document = example_document()
    strategy = dict(document["strategy"])  # type: ignore[arg-type]
    strategy.update(change)
    document["strategy"] = strategy
    with pytest.raises(StrategyValidationError, match=message):
        validate_strategy(document)
