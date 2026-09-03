import pytest

from research.llm.contracts import (
    CANONICAL_CONDITION_OPERATORS,
    CANONICAL_TIMEFRAMES,
    canonical_intent_instruction,
    require_canonical_dot_path,
)


def test_canonical_vocabulary_is_single_and_ordered() -> None:
    assert CANONICAL_TIMEFRAMES == ("1m", "5m", "15m", "1h", "1d", "1w", "1mo")
    assert CANONICAL_CONDITION_OPERATORS == (
        "cross_above",
        "cross_below",
        "less_than",
        "less_equal",
        "greater_than",
        "greater_equal",
        "equal",
    )


@pytest.mark.parametrize("path", ["entry.conditions.0", "features.vix_rsi", "risk.stop_loss_pct"])
def test_canonical_path_accepts_dotted_names(path: str) -> None:
    assert require_canonical_dot_path(path) == path


@pytest.mark.parametrize(
    "path", ["/entry/conditions/0", "entry.conditions[0]", "entry..conditions"]
)
def test_canonical_path_rejects_legacy_notation(path: str) -> None:
    with pytest.raises(ValueError, match="canonical path"):
        require_canonical_dot_path(path)


def test_intent_instruction_forbids_legacy_output_and_names_all_contracts() -> None:
    instruction = canonical_intent_instruction()
    assert "canonical typed operation" in instruction
    assert "Never use JSON Patch" in instruction
    assert "greater_than" in instruction
    assert "entry.conditions.<index>" in instruction
    assert "indicators.<alias>" in instruction
    assert "features.<alias>" in instruction
    assert "Never use bracket or slash paths in output" in instruction


def test_repair_instruction_adds_independent_and_registered_scope() -> None:
    instruction = canonical_intent_instruction(repair=True)
    assert instruction.startswith("Act as an independent intent repair agent")
    assert "Use only registered feature selections" in instruction
