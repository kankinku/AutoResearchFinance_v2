"""Exact two-parent StrategyIR crossover, opt-in development-only.

Only the registered mutation engine's dependency-checked EXIT crossover is
supported. A signed research parent supplies entry/risk and an independently
signed donor supplies exit + its dependencies. This does not approve a strategy.
"""

from __future__ import annotations

from core.integrity.hashes import content_hash
from experiments.identity import semantic_strategy_hash
from mutation.engine import MutationError, MutationOperation, apply_operations
from strategy_ir.schema import StrategyIR


def crossover_exit(primary: StrategyIR, donor: StrategyIR) -> tuple[StrategyIR, dict[str, object]]:
    primary_hash = semantic_strategy_hash(primary)
    donor_hash = semantic_strategy_hash(donor)
    if primary_hash == donor_hash:
        raise ValueError("CROSSOVER_PARENTS_IDENTICAL")
    if primary.schema_version != donor.schema_version or primary.family != donor.family:
        raise ValueError("CROSSOVER_INCOMPATIBLE_SCHEMA_OR_FAMILY")
    if primary.entry.model_dump(mode="json") == donor.entry.model_dump(
        mode="json"
    ) and primary.exit.model_dump(mode="json") == donor.exit.model_dump(mode="json"):
        raise ValueError("CROSSOVER_NO_SIGNAL_STRUCTURE_DIFFERENCE")
    if primary.exit.model_dump(mode="json") == donor.exit.model_dump(mode="json"):
        raise ValueError("CROSSOVER_DONOR_EXIT_UNCHANGED")
    try:
        child = apply_operations(primary, [MutationOperation("CROSSOVER", other=donor)])
    except MutationError as exc:
        raise ValueError("CROSSOVER_INCOMPATIBLE_INDICATOR_DEPENDENCIES") from exc
    child_hash = semantic_strategy_hash(child)
    if child_hash in {primary_hash, donor_hash}:
        raise ValueError("CROSSOVER_NO_NOVEL_SEMANTIC_CHILD")
    if child.entry.model_dump(mode="json") != primary.entry.model_dump(mode="json"):
        raise ValueError("CROSSOVER_PRIMARY_ENTRY_CHANGED")
    if child.risk.model_dump(mode="json") != primary.risk.model_dump(mode="json"):
        raise ValueError("CROSSOVER_PRIMARY_RISK_CHANGED")
    if child.exit.model_dump(mode="json") != donor.exit.model_dump(mode="json"):
        raise ValueError("CROSSOVER_DONOR_EXIT_NOT_ADOPTED")
    return child, {
        "schema": "guided-two-parent-exit-crossover-v1",
        "primary_semantic_hash": primary_hash,
        "donor_semantic_hash": donor_hash,
        "hybrid_semantic_hash": child_hash,
        "hybrid_ir_hash": content_hash(child.model_dump(mode="json", by_alias=True)),
        "adopted_component": "exit",
        "copied_missing_referenced_indicator_dependencies": True,
        "production_approval": False,
        "sealed_oos_evaluated": False,
    }
