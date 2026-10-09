"""Execution-level strategy identity, independent from proposal ancestry."""

from __future__ import annotations

from core.integrity.hashes import content_hash
from strategy_ir.schema import StrategyIR


def semantic_strategy_hash(strategy: StrategyIR) -> str:
    """Hash the executable signal/risk semantics, not the lineage metadata."""
    payload = strategy.model_dump(mode="json", by_alias=True)
    for metadata in ("id", "parents", "generation", "research", "provenance", "family"):
        payload.pop(metadata, None)
    return content_hash(payload)
