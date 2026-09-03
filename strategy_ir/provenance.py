from __future__ import annotations

from pathlib import Path

from strategy_ir.schema import Provenance, StrategyIR


def with_provenance(
    strategy: StrategyIR, path: Path, source_hash: str, source_type: str
) -> StrategyIR:
    """Attach one canonical source record to a normalized Strategy IR."""

    return strategy.model_copy(
        update={
            "provenance": Provenance(
                source_path=path.as_posix(), source_hash=source_hash, source_type=source_type
            )
        }
    )
