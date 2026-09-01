from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from strategy_ir.schema import Condition, StrategyIR


class StrategyValidationError(ValueError):
    """Raised when an IR is structurally valid but semantically unusable."""


_PRICE_FIELDS = {"open", "high", "low", "close", "volume"}
_CROSS_OPERATORS = {"cross_above", "cross_below"}
_COMPARISON_OPERATORS = {"less_than", "less_equal", "greater_than", "greater_equal", "equal"}


def validate_strategy(document: dict[str, Any] | StrategyIR) -> StrategyIR:
    try:
        strategy = (
            document if isinstance(document, StrategyIR) else StrategyIR.model_validate(document)
        )
    except ValidationError as exc:
        raise StrategyValidationError(str(exc)) from exc

    references = set(strategy.indicators) | set(strategy.features) | _PRICE_FIELDS
    for section_name, rules in (("entry", strategy.entry), ("exit", strategy.exit)):
        if not rules.conditions:
            raise StrategyValidationError(f"{section_name} requires at least one condition")
        for condition in rules.conditions:
            _validate_condition(condition, references, section_name)
    for condition in strategy.regime_filters:
        _validate_condition(condition, references, "regime_filters")
    if strategy.entry.logic not in {"AND", "OR"} or strategy.exit.logic not in {"AND", "OR"}:
        raise StrategyValidationError("logic must be AND or OR")
    return strategy


def _validate_condition(condition: Condition, references: set[str], section_name: str) -> None:
    if condition.left not in references:
        raise StrategyValidationError(f"unknown reference {condition.left!r} in {section_name}")
    if condition.op in _CROSS_OPERATORS:
        if condition.right is None or condition.right not in references:
            raise StrategyValidationError(
                f"unknown reference {condition.right!r} in {section_name}"
            )
        if condition.value is not None:
            raise StrategyValidationError(f"cross operator cannot use value in {section_name}")
    elif condition.op in _COMPARISON_OPERATORS:
        if condition.value is None:
            raise StrategyValidationError(f"comparison requires value in {section_name}")
        if condition.right is not None:
            raise StrategyValidationError(f"comparison cannot use right in {section_name}")
    else:
        raise StrategyValidationError(f"unsupported operator {condition.op!r}")
