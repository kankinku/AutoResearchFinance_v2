"""Read-only, cross-generation/attempt train-history aggregation acceptance."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore, digest
from memory.training_trace_store import CandidateTrainingReturns, TrainingTrace, TrainingTraceStore
from memory.trial_inventory import research_trial_inventory


def record(
    state: Path, run: str, generation: int, *,
    include_trace: bool = True,
    source_override: str | None = None,
    code_variant: str = "test-code-hash",
    cutoff_length: int = 40,
    semantic: tuple[str, ...] = ("a" * 64, "b" * 64),
) -> None:
    store = EvidenceStore(state)
    conditions = {
        "dataset_hash": "test-development-data",
        "data_zone": "development",
        "timeframe": "1d",
        "calendar": "us_equities",
        "code_hash": code_variant,
    }
    manifest_key = digest(conditions)
    store.append("run", f"run:{run}", {
        "research_run_id": run, "requested_generations": 1, "seed": 42,
    })
    store.append("manifest", f"manifest:{run}", {
        "research_run_id": run, "comparison_key": manifest_key, **conditions,
    })
    times = tuple(
        (datetime(2024, 1, 2, tzinfo=timezone.utc)+timedelta(days=i+1)).isoformat()
        for i in range(cutoff_length)
    )
    ref = None
    if include_trace:
        rows = tuple(CandidateTrainingReturns(s, tuple(
            ((1 if (index+j)%3 == 0 else -1) / 100)
            for index in range(cutoff_length)
        )) for j,s in enumerate(semantic))
        trace = TrainingTrace(
            source_override or conditions["dataset_hash"], "1d", "us_equities",
            times, rows,
        )
        ref = TrainingTraceStore(state).write(trace)
    store.append("attempt", f"attempt:{run}:{generation}", {
        "research_run_id": run, "attempt_id": f"{run}:{generation}",
        "generation": generation, "status": "COMPLETED",
        "training_trace_ref": ref,
        "candidates": [
            {"candidate_hash": s, "semantic_strategy_hash": s,
             "status": "REJECT", "family": "trend", "failed_gates": []}
            for s in semantic
        ],
    })
    store.append("generation", f"generation:{run}:{generation}", {
        "research_run_id": run, "generation": generation,
        "attempt_id": f"{run}:{generation}",
        "status": "COMPLETED", "duplicate_skipped": 0,
    })
    store.append("end", f"end:{run}", {"research_run_id": run, "status": "COMPLETED"})


def test_cross_generation_history_aligns_without_duplicate_semantic_inflation(
    tmp_path: Path,
) -> None:
    record(tmp_path/"first", "run-1", 1, cutoff_length=45)
    record(tmp_path/"second", "run-2", 1, cutoff_length=40)
    report = research_trial_inventory((tmp_path/"first", tmp_path/"second"))
    assert report["cross_generation_aligned_scopes"] == 1
    assert report["cross_generation_incomplete_scopes"] == 0
    item = report["cross_generation_training_history"][0]
    assert item["status"] == "ALIGNED_TRAIN_ONLY"
    assert item["aligned_observations"] == 40
    assert item["candidate_evaluation_instances"] == 4
    assert item["unique_semantic_candidates"] == 2
    assert item["duplicate_semantic_instances"] == 2
    assert item["iid_equivalent_trials_estimate"] is not None
    assert item["global_dsr_approved"] is False
    assert report["effective_independent_trials"] is None
    assert "returns" not in str(report)


def test_partial_history_cannot_be_reinterpreted_as_complete(tmp_path: Path) -> None:
    record(tmp_path/"first", "run-1", 1)
    record(tmp_path/"second", "run-2", 1, include_trace=False)
    report = research_trial_inventory((tmp_path/"first", tmp_path/"second"))
    item = report["cross_generation_training_history"][0]
    assert item["status"] == "INCOMPLETE_TRAINING_TRACE_HISTORY"
    assert item["iid_equivalent_trials_estimate"] is None
    assert report["cross_generation_aligned_scopes"] == 0
    assert report["effective_independent_trials"] is None


def test_mismatched_manifest_source_and_snapshot_rejected(tmp_path: Path) -> None:
    record(tmp_path/"a", "run-a", 1, source_override="unrelated-source")
    with pytest.raises(EvidenceIntegrityError, match="manifest|source"):
        research_trial_inventory((tmp_path/"a",))


def test_tampered_or_missing_trace_never_becomes_measured(tmp_path: Path) -> None:
    folder = tmp_path/"a"
    record(folder, "run-a", 1)
    file = next((folder/"system"/"training-traces").glob("*.json"))
    file.write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="checksum"):
        research_trial_inventory((folder,))


def test_different_manifest_scopes_never_pooled(tmp_path: Path) -> None:
    record(tmp_path/"a", "run-a", 1)
    record(tmp_path/"b", "run-b", 1, code_variant="other-code")
    report = research_trial_inventory((tmp_path/"a", tmp_path/"b"))
    assert report["cross_generation_aligned_scopes"] == 0
    assert len(report["cross_generation_training_history"]) == 2
    assert all(item["status"] == "INSUFFICIENT_CROSS_GENERATION_HISTORY"
               for item in report["cross_generation_training_history"])
