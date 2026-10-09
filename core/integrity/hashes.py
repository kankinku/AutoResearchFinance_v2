from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from foundation.hashes import canonical_bytes as canonical_bytes
from foundation.hashes import content_hash as content_hash


def experiment_hash(
    *,
    strategy_ir: Mapping[str, Any],
    parameters: Mapping[str, Any],
    symbols: Sequence[str],
    start_date: str,
    end_date: str,
    dataset_version: str,
    evaluator_version: str,
    cost_model_version: str,
    compiler_version: str,
    image_digest: str,
    seed: int,
) -> str:
    manifest = {
        "strategy_ir": strategy_ir,
        "parameters": parameters,
        "symbols": list(symbols),
        "start_date": start_date,
        "end_date": end_date,
        "dataset_version": dataset_version,
        "evaluator_version": evaluator_version,
        "cost_model_version": cost_model_version,
        "compiler_version": compiler_version,
        "image_digest": image_digest,
        "seed": seed,
    }
    return content_hash(manifest)
