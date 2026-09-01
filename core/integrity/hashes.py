from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible values deterministically for content hashing."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


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
