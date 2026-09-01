from __future__ import annotations

from strategy_ir.compiler import compile_strategy
from strategy_ir.validator import validate_strategy
from tests.strategy_ir.test_schema import example_document


def test_compiler_returns_artifact_with_ir_hash_and_no_network_or_orders() -> None:
    strategy = validate_strategy(example_document())

    artifact = compile_strategy(strategy)

    assert artifact.manifest["strategy_hash"]
    assert artifact.manifest["compiler_version"] == "compiler-v1"
    assert "def evaluate_strategy" in artifact.source
    assert "import requests" not in artifact.source
    assert "place_order" not in artifact.source


def test_compiler_is_deterministic() -> None:
    strategy = validate_strategy(example_document())

    assert compile_strategy(strategy) == compile_strategy(strategy)
