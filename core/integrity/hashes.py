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
    dataset_hash: str | None = None,
    benchmark_hash: str | None = None,
    feature_inputs_hash: str | None = None,
    code_hash: str | None = None,
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
    for key, value in (
        ("dataset_hash", dataset_hash),
        ("benchmark_hash", benchmark_hash),
        ("feature_inputs_hash", feature_inputs_hash),
        ("code_hash", code_hash),
    ):
        if value is not None:
            manifest[key] = value
    return content_hash(manifest)
