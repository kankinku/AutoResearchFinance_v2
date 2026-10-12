"""CPCV path and fold-selection regression fixtures."""

from datetime import datetime, timedelta, timezone
from itertools import combinations
from math import comb

import pytest

from core.data.contracts import Bar, MarketDataSet
from core.validation.cpcv import cpcv_splits
from experiments.candidate_generator import generate_candidates
from mutation.parameter import ParameterDomain
from orchestration.purged_cpcv import assign_paths, run_purged_cpcv
from tests.orchestration.test_train_only_selection import strategy


@pytest.mark.parametrize("n,k", [(3, 1), (4, 2), (5, 2), (6, 2), (6, 3), (8, 4)])
def test_reconstruction_uses_each_group_and_split_edge_once(n: int, k: int) -> None:
    splits = tuple(combinations(range(n), k))
    paths = assign_paths(n, k, splits)
    assert len(paths) == comb(n - 1, k - 1)
    observed = [(split, group) for path in paths for group, split in path.items()]
    expected = [(i, group) for i, groups in enumerate(splits) for group in groups]
    assert sorted(observed) == sorted(expected)
    assert all(set(path) == set(range(n)) for path in paths)
    assert all(len(set(path.values())) == n for path in paths)


def fixture():
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            "AAA",
            100.0,
            100.0,
            100.0,
            100.0,
            1000.0,
        )
        for i in range(16)
    )
    candidates = generate_candidates(
        strategy(),
        (),
        (ParameterDomain("risk.position_size_pct", (50.0, 100.0)),),
        method="grid",
        count=2,
        seed=6,
    )
    return MarketDataSet("cpcv-v1", "development", bars), candidates


def test_purged_refit_and_oos_paths_are_exact_and_bounded() -> None:
    dataset, candidates = fixture()
    calls = []

    def score(candidate, data, start):
        times = tuple(sorted({b.timestamp for b in data.bars}))
        calls.append((candidate.candidate_hash, times, start))
        if start is None:
            return (0.01 if candidate == candidates[0] else 0.02) * (1 if len(times) % 2 else -1)
        return 0.01 if candidate == candidates[0] else 0.02

    labels = tuple(min(i + 1, 15) for i in range(16))
    report = run_purged_cpcv(
        dataset=dataset,
        candidates=candidates,
        evaluate=score,
        label_end_indices=labels,
        embargo_bars=1,
    )
    assert report.status == "EVALUATED_RETROSPECTIVE"
    assert report.chronological_train_only is False
    assert report.sealed_oos_evaluated is False
    assert len(report.folds) == 6
    assert len(report.paths) == 3
    expected_splits = cpcv_splits(
        tuple(range(16)),
        groups=4,
        test_groups=2,
        label_end_indices=labels,
        embargo_bars=1,
    )
    for fold, (train, test) in zip(report.folds, expected_splits, strict=True):
        assert (fold.train_indices, fold.test_indices) == (train, test)
        assert not set(train) & set(test)
        assert fold.selected_hash in {c.candidate_hash for c in candidates}
        assert len(fold.test_blocks) == 2
    seen = {(block.split, block.group) for path in report.paths for block in path.blocks}
    assert len(seen) == 12
    assert all(len(path.blocks) == 4 for path in report.paths)
    test_calls = {(h, start, times[-1]) for h, times, start in calls if start is not None}
    for path in report.paths:
        factor = 1.0
        for block in path.blocks:
            assert (
                block.candidate_hash,
                datetime.fromisoformat(block.start_at),
                datetime.fromisoformat(block.end_at),
            ) in test_calls
            factor *= 1 + block.total_return
        assert path.total_return == pytest.approx(factor - 1)


def test_missing_label_metadata_and_negative_embargo_fail_closed() -> None:
    dataset, candidates = fixture()
    with pytest.raises(ValueError, match="label"):
        run_purged_cpcv(
            dataset=dataset,
            candidates=candidates,
            evaluate=lambda *args: 0.0,
            label_end_indices=(0,),
            embargo_bars=1,
        )
    with pytest.raises(ValueError, match="embargo"):
        run_purged_cpcv(
            dataset=dataset,
            candidates=candidates,
            evaluate=lambda *args: 0.0,
            label_end_indices=tuple(range(16)),
            embargo_bars=-1,
        )


def test_generation_pipeline_explicit_cpcv_opt_in() -> None:
    from evaluation.selector import FunnelConfig
    from orchestration.pipeline import GenerationPipeline

    dataset, _ = fixture()
    result = GenerationPipeline().run(
        parent=strategy(),
        dataset=dataset,
        operations=(),
        domains=(ParameterDomain("risk.position_size_pct", (50.0, 100.0)),),
        method="grid",
        count=2,
        seed=6,
        funnel=FunnelConfig(
            min_fast_trades=0,
            min_full_trades=0,
            min_fast_return=-1,
            min_full_return=-1,
            min_robust_score=0,
            require_validation=False,
        ),
        cpcv_label_end_indices=tuple(range(16)),
        cpcv_embargo_bars=1,
    )
    assert result.purged_cpcv is not None
    assert result.purged_cpcv.status == "EVALUATED_RETROSPECTIVE"
    assert len(result.purged_cpcv.folds) == 6
    assert len(result.purged_cpcv.paths) == 3
    assert result.purged_cpcv.sealed_oos_evaluated is False


def test_worker_cpcv_options_survive_serialization(tmp_path) -> None:
    from runtime.job_protocol import EvaluationJobRequest

    request = EvaluationJobRequest.from_evaluation_kwargs(
        tmp_path,
        {
            "source_path": "strategy.yaml",
            "data_path": "bars.parquet",
            "cpcv_label_end_indices": tuple(range(16)),
            "cpcv_embargo_bars": 1,
        },
    )
    restored = EvaluationJobRequest.model_validate_json(request.model_dump_json())
    kwargs = restored.evaluation_kwargs(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        execution_context={},
    )
    assert kwargs["cpcv_label_end_indices"] == tuple(range(16))
    assert kwargs["cpcv_embargo_bars"] == 1


def test_evaluation_service_worker_persists_explicit_cpcv_evidence(tmp_path) -> None:
    from application.evaluation_service import EvaluationService
    from core.data.parquet import ParquetDataProvider
    from memory.evidence_store import EvidenceStore

    dataset, _ = fixture()
    source = tmp_path / "source.json"
    source.write_text(strategy().model_dump_json(by_alias=True), encoding="utf-8")
    datafile = tmp_path / "development.parquet"
    ParquetDataProvider.write(datafile, dataset)
    service = EvaluationService(project_root=tmp_path, state_dir=tmp_path / "state")
    result = service.run(
        source_path="source.json",
        data_path="development.parquet",
        method="grid",
        count=2,
        min_trades=0,
        min_annual_trades=0,
        parameter_domains=(ParameterDomain("risk.position_size_pct", (50.0, 100.0)),),
        cpcv_label_end_indices=tuple(range(16)),
        cpcv_embargo_bars=1,
    )
    assert result["status"] == "COMPLETED"
    report = result["purged_cpcv"]
    assert report["status"] == "EVALUATED_RETROSPECTIVE"
    assert len(report["paths"]) == 3
    assert report["sealed_oos_evaluated"] is False
    events = EvidenceStore(tmp_path / "state").events()
    attempts = [item["payload"] for item in events if item["kind"] == "attempt"]
    assert len(attempts) == 1
    assert attempts[0]["purged_cpcv"]["status"] == "EVALUATED_RETROSPECTIVE"
    assert len(attempts[0]["purged_cpcv"]["paths"]) == 3


def test_held_out_prices_cannot_change_the_same_folds_training_choice() -> None:
    dataset, candidates = fixture()
    from dataclasses import replace

    from core.data.contracts import MarketDataSet

    changed = MarketDataSet(
        dataset.version,
        dataset.zone,
        tuple(
            replace(bar, open=150.0, high=150.0, low=150.0, close=150.0) if i < 4 else bar
            for i, bar in enumerate(dataset.bars)
        ),
        dataset.timeframe,
        dataset.calendar,
        dataset.provenance,
    )

    def score(candidate, data, start):
        if start is not None:
            return 0.01
        factor = 1 if candidate == candidates[0] else -1
        return factor * (data.bars[-1].close / 100.0 - 1.0) * 0.1

    kwargs = {
        "candidates": candidates,
        "evaluate": score,
        "label_end_indices": tuple(range(16)),
        "embargo_bars": 0,
    }
    base = run_purged_cpcv(dataset=dataset, **kwargs)
    altered = run_purged_cpcv(dataset=changed, **kwargs)
    # Split 1 tests groups 0 and 2. Neither may train that split.
    assert base.folds[1].test_indices == altered.folds[1].test_indices
    assert set(range(4)).issubset(base.folds[1].test_indices)
    assert base.folds[1].training_score == altered.folds[1].training_score
    assert base.folds[1].selected_hash == altered.folds[1].selected_hash
