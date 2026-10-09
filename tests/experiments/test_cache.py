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


def test_cache_key_changes_with_dataset_content_even_if_version_is_unchanged(
    tmp_path: Path,
) -> None:
    cache = ExperimentCache(tmp_path / "experiments.sqlite")
    first = manifest(dataset_hash="sha256:first-data-bytes")
    cache.store(first, {"status": "SUCCEEDED"})
    assert cache.lookup(first).status == "CACHE_HIT"
    assert cache.lookup(manifest(dataset_hash="sha256:revised-data-bytes")).status == "CACHE_MISS"
    cache.close()


def test_cache_key_accounts_for_feature_benchmark_and_worker_code(tmp_path: Path) -> None:
    cache = ExperimentCache(tmp_path / "experiments.sqlite")
    reference = manifest(
        dataset_hash="bars-h1",
        benchmark_hash="index-h1",
        feature_inputs_hash="feature-h1",
        code_hash="worker-h1",
    )
    cache.store(reference, {"status": "SUCCEEDED"})
    baseline = dict(
        dataset_hash="bars-h1",
        benchmark_hash="index-h1",
        feature_inputs_hash="feature-h1",
        code_hash="worker-h1",
    )
    for field in ("benchmark_hash", "feature_inputs_hash", "code_hash"):
        revised_values = {**baseline, field: "changed"}
        assert cache.lookup(manifest(**revised_values)).status == "CACHE_MISS"
    cache.close()


def test_historical_manifest_hash_remains_stable_when_optional_hashes_absent() -> None:
    from core.integrity.hashes import experiment_hash

    current = manifest()
    assert current.experiment_hash == experiment_hash(
        strategy_ir=current.strategy_ir,
        parameters=current.parameters,
        symbols=current.symbols,
        start_date=current.start_date,
        end_date=current.end_date,
        dataset_version=current.dataset_version,
        evaluator_version=current.evaluator_version,
        cost_model_version=current.cost_model_version,
        compiler_version=current.compiler_version,
        image_digest=current.image_digest,
        seed=current.seed,
    )
