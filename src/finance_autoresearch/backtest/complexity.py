from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class StrategyComplexity:
    indicator_count: int
    new_clause_count: int
    regime_branch_count: int
    exit_family_count: int

    def to_payload(self) -> dict[str, int]:
        return {
            "indicator_count": self.indicator_count,
            "new_clause_count": self.new_clause_count,
            "regime_branch_count": self.regime_branch_count,
            "exit_family_count": self.exit_family_count,
        }


def inspect_strategy_complexity(strategy_path: Path | str) -> StrategyComplexity:
    source = Path(strategy_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    indicator_count = 0
    clause_count = 0
    regime_branch_count = 0
    exit_family_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_indicator_call(node):
            indicator_count += 1
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith(("entry_clause_", "risk_clause_")):
                    clause_count += 1
                if isinstance(target, ast.Name) and target.id in {"bull", "bear"}:
                    regime_branch_count += 1
                if isinstance(target, ast.Name) and target.id in {"long_exits", "short_exits"}:
                    exit_family_count += 1
    return StrategyComplexity(
        indicator_count=indicator_count,
        new_clause_count=clause_count,
        regime_branch_count=regime_branch_count,
        exit_family_count=exit_family_count,
    )


def _is_indicator_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    owner = func.value
    if not isinstance(owner, ast.Attribute):
        return False
    return isinstance(owner.value, ast.Name) and owner.value.id == "context" and owner.attr == "indicators"
