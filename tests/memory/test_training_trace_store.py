"""Content-addressed, immutable, development train-only candidate return traces."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from memory.evidence_store import EvidenceIntegrityError
from memory.training_trace_store import (
    CandidateTrainingReturns,
    TrainingTrace,
    TrainingTraceStore,
    align_training_traces,
)


def trace(candidates: tuple[str, ...] = ("a", "b"), bars: int = 40) -> TrainingTrace:
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    times = tuple((start + timedelta(days=i)).isoformat() for i in range(1, bars + 1))
    items = tuple(
        CandidateTrainingReturns(identity, tuple(
            (0.01 if (i+j) % 3 == 0 else -0.005)
            for i in range(bars)
        ))
        for j, identity in enumerate(candidates)
    )
    return TrainingTrace(
        dataset_hash="data-hash", timeframe="1d", calendar="us_equities",
        timestamps=times, candidates=items,
    )


def test_immutable_trace_addressed_by_checksum_and_read_only(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = TrainingTraceStore(state)
    obj = trace()
    reference = store.write(obj)
    assert len(reference) == 64
    assert store.write(obj) == reference
    assert store.read(reference) == obj
    assert len(list((state / "system" / "training-traces").glob("*.json"))) == 1


def test_tampered_trace_fails_and_original_is_never_repaired(tmp_path: Path) -> None:
    store = TrainingTraceStore(tmp_path)
    ref = store.write(trace())
    dest = tmp_path / "system" / "training-traces" / f"{ref}.json"
    dest.write_text('{"forged":true}', encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="checksum|invalid"):
        store.read(ref)
    with pytest.raises(EvidenceIntegrityError):
        store.write(trace())
    assert dest.read_text(encoding="utf-8") == '{"forged":true}'


@pytest.mark.parametrize("bad", [
    "x" * 64, "../evil", "123", "G" * 64,
])
def test_invalid_or_missing_references_fail_closed(tmp_path: Path, bad: str) -> None:
    store = TrainingTraceStore(tmp_path)
    with pytest.raises(EvidenceIntegrityError):
        store.read(bad)
    assert not (tmp_path / "system").exists()


def test_train_only_traces_align_on_common_prefix_and_deduplicate_semantics(
    tmp_path: Path,
) -> None:
    store = TrainingTraceStore(tmp_path)
    one = trace(("a", "b"), 40)
    two = trace(("a", "c"), 35)
    refs = (store.write(one), store.write(two))
    result = align_training_traces((store.read(refs[0]), store.read(refs[1])))
    assert result.status == "ALIGNED_TRAIN_ONLY"
    assert result.aligned_observations == 35
    assert result.candidate_evaluation_instances == 4
    assert result.unique_semantic_candidates == 3
    assert result.duplicate_semantic_instances == 1
    assert result.dsr_approved is False
    assert result.training_cutoff_at == two.timestamps[-1]
    assert result.cohort_dependence is not None
    assert result.cohort_dependence.dsr_calibrated is False


def test_misaligned_timestamps_and_source_identity_are_not_blended() -> None:
    from dataclasses import replace

    one = trace(("a", "b"), 40)
    changed = replace(one, timestamps=tuple(
        ("2024-01-08T12:00:00+00:00" if i == 5 else timestamp)
        for i, timestamp in enumerate(one.timestamps)
    ))
    result = align_training_traces((one, changed))
    assert result.status == "INCOMPARABLE_TIMEBASE"
    assert result.cohort_dependence is None
    changed_source = replace(one, dataset_hash="a-different-dataset")
    assert align_training_traces((one, changed_source)).status == "INCOMPARABLE_SOURCE"


def test_inconsistent_duplicate_semantic_returns_fail_closed() -> None:
    from dataclasses import replace

    one = trace(("a", "b"))
    changed = replace(one, candidates=(
        CandidateTrainingReturns("a", tuple(0.02 if i % 3 == 0 else -0.005 for i in range(40))),
        one.candidates[1],
    ))
    result = align_training_traces((one, changed))
    assert result.status == "INCONSISTENT_SEMANTIC_RETURNS"
    assert result.cohort_dependence is None


def test_invalid_values_and_duplicate_semantic_ids_rejected(tmp_path: Path) -> None:
    store = TrainingTraceStore(tmp_path)
    baseline = trace()
    bad = TrainingTrace(
        baseline.dataset_hash, baseline.timeframe, baseline.calendar,
        baseline.timestamps, (baseline.candidates[0], baseline.candidates[0]),
    )
    with pytest.raises(EvidenceIntegrityError, match="duplicate"):
        store.write(bad)
    nan_bad = TrainingTrace(
        baseline.dataset_hash, baseline.timeframe, baseline.calendar,
        baseline.timestamps,
        (CandidateTrainingReturns("a", (float("nan"),) * 40),),
    )
    with pytest.raises(EvidenceIntegrityError, match="finite"):
        store.write(nan_bad)
    assert not (tmp_path / "system").exists()


def test_short_common_prefix_is_insufficient_without_interpolation() -> None:
    one = trace(("a", "b"), 40)
    two = trace(("c",), 25)
    result = align_training_traces((one, two))
    assert result.status == "INSUFFICIENT_ALIGNED_HISTORY"
    assert result.cohort_dependence is None
