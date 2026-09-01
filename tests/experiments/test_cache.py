from __future__ import annotations

from pathlib import Path

from experiments.cache import ExperimentCache
from experiments.manifest import ExperimentManifest


def manifest(**changes: object) -> ExperimentManifest:
    values: dict[str, object] = {
        "strategy_ir": {"id": "S1"},
        "parameters": {"fast": 12},
        "symbols": ("TEST",),
        "start_date": "2020-01-01",
        "end_date": "2024-01-01",
        "dataset_version": "data-v1",
        "evaluator_version": "eval-v1",
        "cost_model_version": "cost-v1",
        "compiler_version": "compiler-v1",
        "image_digest": "sha256:image",
        "seed": 7,
    }
    values.update(changes)
    return ExperimentManifest(**values)  # type: ignore[arg-type]


def test_cache_miss_then_hit_is_idempotent(tmp_path: Path) -> None:
    cache = ExperimentCache(tmp_path / "experiments.sqlite")
    current = manifest()

    assert cache.lookup(current).status == "CACHE_MISS"
    cache.store(current, {"exit_status": "SUCCEEDED", "return": 0.12})
    hit = cache.lookup(current)

    assert hit.status == "CACHE_HIT"
    assert hit.result == {"exit_status": "SUCCEEDED", "return": 0.12}
    cache.close()


def test_relevant_version_change_is_cache_miss_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "experiments.sqlite"
    first = manifest()
    cache = ExperimentCache(path)
    cache.store(first, {"exit_status": "SUCCEEDED"})
    cache.close()

    reopened = ExperimentCache(path)
    assert reopened.lookup(first).status == "CACHE_HIT"
    assert reopened.lookup(manifest(evaluator_version="eval-v2")).status == "CACHE_MISS"
    assert reopened.lookup(manifest(cost_model_version="cost-v2")).status == "CACHE_MISS"
    assert reopened.lookup(manifest(dataset_version="data-v2")).status == "CACHE_MISS"
    reopened.close()
