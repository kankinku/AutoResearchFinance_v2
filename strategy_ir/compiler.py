from __future__ import annotations

import json
from dataclasses import dataclass

from core.integrity.hashes import content_hash
from strategy_ir.schema import StrategyIR

COMPILER_VERSION = "compiler-v1"


@dataclass(frozen=True)
class CompiledArtifact:
    source: str
    manifest: dict[str, str]


def compile_strategy(strategy: StrategyIR) -> CompiledArtifact:
    canonical = strategy.model_dump(mode="json", by_alias=True, exclude={"provenance"})
    strategy_hash = content_hash(canonical)
    embedded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    source = (
        "# Generated execution artifact; edit Strategy IR instead.\n"
        f"# strategy_hash={strategy_hash}\n"
        "STRATEGY_CONFIG = "
        f"{embedded}\n\n"
        "def evaluate_strategy(data):\n"
        "    return {\"strategy_hash\": STRATEGY_CONFIG[\"id\"], \"rows\": len(data)}\n"
    )
    return CompiledArtifact(
        source=source,
        manifest={"strategy_hash": strategy_hash, "compiler_version": COMPILER_VERSION},
    )
