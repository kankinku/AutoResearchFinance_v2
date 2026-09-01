from __future__ import annotations

from pathlib import Path

import pytest

from core.evaluator.immutable_guard import is_protected_path, protected_roots


def test_protected_roots_are_repository_relative() -> None:
    assert protected_roots() == (
        Path("core/data"),
        Path("core/backtest"),
        Path("core/evaluator"),
        Path("core/validation"),
        Path("core/costs"),
        Path("core/integrity"),
    )


@pytest.mark.parametrize(
    "candidate",
    ["core/evaluator/scoring.py", "core/integrity/hashes.py", "core/data/x.parquet"],
)
def test_protected_root_matching_is_component_aware(candidate: str) -> None:
    assert is_protected_path(Path(candidate))
    assert not is_protected_path(Path("core/evaluation-not-core/file.py"))
