"""Strategy IR compiler may share canonical serialization but not import finance core."""
from __future__ import annotations

import ast
from pathlib import Path

from core.integrity.hashes import content_hash
from strategy_ir.compiler import compile_strategy
from strategy_ir.schema import StrategyIR
from tests.strategy_ir.test_schema import example_document


def test_compiler_does_not_depend_on_financial_core_for_hashing() -> None:
    filename = Path(__file__).parents[2] / "strategy_ir" / "compiler.py"
    imports = [
        node.module
        for node in ast.walk(ast.parse(filename.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    ]
    assert not any(name and name.startswith("core.") for name in imports)


def test_compiled_hash_remains_compatible_with_integrity_contract() -> None:
    strategy = StrategyIR.model_validate(example_document())
    canonical = strategy.model_dump(mode="json", by_alias=True, exclude={"provenance"})
    assert compile_strategy(strategy).manifest["strategy_hash"] == content_hash(canonical)


def test_foundation_hashing_package_is_shipped_and_type_checked() -> None:
    import pytest

    tomllib = pytest.importorskip("tomllib")
    root = Path(__file__).parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    includes = config["tool"]["setuptools"]["packages"]["find"]["include"]
    mypy_packages = config["tool"]["mypy"]["packages"]
    assert "foundation*" in includes
    assert "foundation" in mypy_packages
