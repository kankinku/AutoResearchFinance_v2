"""Execution identity is independent of proposal lineage and display IDs."""

from __future__ import annotations

from experiments.candidate_generator import Candidate
from experiments.deduplicator import deduplicate_candidates
from experiments.identity import semantic_strategy_hash
from strategy_ir.schema import StrategyIR


def _strategy(identifier: str) -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": identifier,
            "family": "trend",
            "generation": 1,
            "indicators": {"slow": {"type": "SMA", "period": 5}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "less_than", "left": "close", "value": 0}],
            },
            "risk": {"stop_loss_pct": 3, "take_profit_pct": 10},
        }
    )


def test_strategy_semantic_hash_ignores_ir_lineage_but_not_execution() -> None:
    first = _strategy("A")
    another_parent = _strategy("B")
    another_parent.parents = ["older-parent"]
    another_parent.generation = 12
    another_parent.research.mutation = ["repaired"]
    another_parent.provenance.source_path = "different.yaml"
    assert semantic_strategy_hash(first) == semantic_strategy_hash(another_parent)
    another_parent.risk.stop_loss_pct = 7
    assert semantic_strategy_hash(first) != semantic_strategy_hash(another_parent)


def test_semantic_dedup_keeps_first_candidate_and_allows_legacy_mode() -> None:
    first = Candidate(_strategy("A"), {}, (), "parent-A", "lineage-A")
    second = Candidate(_strategy("B"), {}, (), "parent-B", "lineage-B")
    assert deduplicate_candidates([first, second]).unique == (first, second)
    result = deduplicate_candidates([first, second], semantic=True)
    assert result.unique == (first,)
    assert result.duplicate_hashes == ("lineage-B",)
