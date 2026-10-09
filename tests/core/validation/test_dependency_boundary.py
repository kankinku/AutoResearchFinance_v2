"""The financial core must not depend on postprocessing/evaluation models."""

from __future__ import annotations

import ast
from pathlib import Path

from core.validation.gates import hard_gate


class _PlainMetrics:
    trade_count = 2
    total_return = 0.15


def test_core_gate_accepts_structural_metrics_without_evaluation_import() -> None:
    path = Path(__file__).parents[3] / "core" / "validation" / "gates.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = (node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
    assert not any(name and name.startswith("evaluation") for name in imports)
    assert hard_gate(_PlainMetrics(), min_trade_count=1, min_return=0.0).passed
