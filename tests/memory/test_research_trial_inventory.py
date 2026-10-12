"""Verified read-only, multi-workspace trial accounting regression contracts."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from memory.trial_inventory import research_trial_inventory


def _run(
    state: Path,
    name: str,
    *,
    key: str | None = "scope-a",
    generation: int = 1,
    statuses: tuple[str, ...] = ("REJECT", "REJECT"),
    hashes: tuple[str, ...] = ("same", "same"),
    finalized: bool = True,
    attempts: int = 1,
    skipped: int | None = 0,
    dependence: dict[str, object] | None = None,
) -> None:
    store = EvidenceStore(state)
    store.append(
        "run",
        "run:" + name,
        {
            "research_run_id": name,
            "requested_generations": 3,
            "seed": 8,
        },
    )
    if key is not None:
        store.append(
            "manifest",
            "manifest:" + name,
            {
                "research_run_id": name,
                "comparison_key": key,
            },
        )
    for counter in range(attempts):
        ident = f"{name}-{counter}"
        store.append(
            "attempt",
            "attempt:" + ident,
            {
                **({"trial_dependence": dependence} if dependence is not None else {}),
                "research_run_id": name,
                "attempt_id": ident,
                "generation": generation,
                "status": "COMPLETED",
                "candidates": [
                    {
                        "candidate_hash": hash_value,
                        "status": status,
                        "family": "trend",
                        "failed_gates": ["quality"],
                    }
                    for hash_value, status in zip(hashes, statuses, strict=True)
                ],
            },
        )
    if finalized:
        gen_payload: dict[str, object] = {
            "research_run_id": name,
            "generation": generation,
            "status": "COMPLETED",
            "attempt_id": f"{name}-{attempts - 1}",
        }
        if skipped is not None:
            gen_payload["duplicate_skipped"] = skipped
        store.append("generation", f"generation:{name}:{generation}", gen_payload)
        store.append(
            "end",
            "end:" + name,
            {
                "research_run_id": name,
                "status": "COMPLETED",
            },
        )


def test_aggregates_attempts_finalized_trials_and_unique_by_comparable_scope(
    tmp_path: Path,
) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    _run(first, "one", hashes=("same", "new"), attempts=2, skipped=1)
    _run(second, "two", hashes=("same", "third"), skipped=2)
    report = research_trial_inventory((first, second))
    assert report["status"] == "OBSERVED"
    assert report["workspace_count"] == 2
    assert report["research_run_count"] == 2
    assert report["evaluation_attempt_count"] == 3
    assert report["candidate_evaluation_instances"] == 6
    assert report["finalized_candidate_instances"] == 4
    assert report["nonfinal_candidate_instances"] == 2
    assert report["unique_candidate_hashes_global"] == 3
    assert report["duplicate_candidate_evaluations_global"] == 3
    assert report["total_skipped_duplicate_candidates"] == 3
    assert report["effective_independent_trials"] is None
    assert report["comparability"] == "MANIFEST_SCOPED_ONLY"
    assert report["scopes"] == [
        {
            "comparison_key": "scope-a",
            "run_count": 2,
            "candidate_evaluation_instances": 6,
            "unique_candidate_hashes": 3,
            "duplicate_candidate_evaluations": 3,
            "manifest_provenance": "SELF_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
            "unique_semantic_strategy_hashes": None,
            "missing_semantic_hash_instances": 6,
        }
    ]


def test_mirrored_workspace_is_counted_once(tmp_path: Path) -> None:
    first, mirror = tmp_path / "one", tmp_path / "mirror"
    _run(first, "shared", hashes=("a", "b"))
    store = EvidenceStore(first)
    other = EvidenceStore(mirror)
    other.path.parent.mkdir(parents=True)
    shutil.copy2(store.path, other.path)
    report = research_trial_inventory((first, mirror, first))
    assert report["workspace_count"] == 2
    assert report["research_run_count"] == 1
    assert report["evaluation_attempt_count"] == 1
    assert report["candidate_evaluation_instances"] == 2
    assert report["duplicate_research_run_copies"] == 1


def test_conflicting_mirror_and_partial_mirror_fail_closed(tmp_path: Path) -> None:
    first, other = tmp_path / "a", tmp_path / "b"
    _run(first, "same", hashes=("a",), statuses=("REJECT",))
    _run(other, "same", hashes=("b",), statuses=("REJECT",))
    with pytest.raises(EvidenceIntegrityError, match="conflicting|mirror"):
        research_trial_inventory((first, other))


def test_missing_manifest_is_not_comparable_with_any_scoped_history(tmp_path: Path) -> None:
    _run(tmp_path / "a", "known", key="scope-a")
    _run(tmp_path / "b", "different", key="scope-b")
    _run(tmp_path / "c", "unscoped", key=None)
    report = research_trial_inventory((tmp_path / "a", tmp_path / "b", tmp_path / "c"))
    assert report["research_run_count"] == 3
    assert report["unscoped_candidate_evaluation_instances"] == 2
    assert len(report["scopes"]) == 2
    assert all(scope["run_count"] == 1 for scope in report["scopes"])
    assert report["history_complete"] is False


def test_unfinalized_and_unverified_attempts_do_not_become_verified_finals(
    tmp_path: Path,
) -> None:
    state = tmp_path / "test"
    _run(state, "open", finalized=False, statuses=("REJECT",), hashes=("a",))
    report = research_trial_inventory((state,))
    assert report["evaluation_attempt_count"] == 1
    assert report["candidate_evaluation_instances"] == 1
    assert report["finalized_candidate_instances"] == 0
    assert report["nonfinal_candidate_instances"] == 1
    assert report["unfinished_research_runs"] == 1
    assert report["history_complete"] is False


def test_unknown_legacy_skip_count_stays_unmeasured(tmp_path: Path) -> None:
    _run(tmp_path, "legacy", skipped=None)
    report = research_trial_inventory((tmp_path,))
    assert report["total_skipped_duplicate_candidates"] is None
    assert report["history_complete"] is False


def test_corrupted_store_is_not_silently_ignored(tmp_path: Path) -> None:
    _run(tmp_path / "one", "valid")
    corrupt = EvidenceStore(tmp_path / "bad")
    corrupt.path.parent.mkdir(parents=True)
    corrupt.path.write_bytes(b"bad sqlite")
    with pytest.raises(EvidenceIntegrityError):
        research_trial_inventory((tmp_path / "one", tmp_path / "bad"))


def test_empty_source_is_read_only_and_reports_no_coverage(tmp_path: Path) -> None:
    state = tmp_path / "missing"
    report = research_trial_inventory((state,))
    assert report["status"] == "EMPTY"
    assert report["history_complete"] is False
    assert report["candidate_evaluation_instances"] == 0
    assert not state.exists()


def test_no_inferred_unregistered_workspaces(tmp_path: Path) -> None:
    _run(tmp_path / "first", "a")
    _run(tmp_path / "sibling", "b")
    report = research_trial_inventory((tmp_path / "first",))
    assert report["workspace_count"] == 1
    assert report["research_run_count"] == 1
    assert report["history_complete"] is False


def test_semantic_identity_unifies_distinct_lineage_hashes(tmp_path: Path) -> None:
    state = tmp_path / "semantic"
    store = EvidenceStore(state)
    store.append(
        "run",
        "run:r",
        {
            "research_run_id": "r",
            "requested_generations": 1,
            "seed": 0,
        },
    )
    store.append(
        "manifest",
        "manifest:r",
        {
            "research_run_id": "r",
            "comparison_key": "matching-inputs",
        },
    )
    store.append(
        "attempt",
        "attempt:one",
        {
            "research_run_id": "r",
            "attempt_id": "one",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "parent-a",
                    "semantic_strategy_hash": "c" * 64,
                    "status": "REJECT",
                    "family": "trend",
                    "failed_gates": [],
                },
                {
                    "candidate_hash": "parent-b",
                    "semantic_strategy_hash": "c" * 64,
                    "status": "REJECT",
                    "family": "trend",
                    "failed_gates": [],
                },
            ],
        },
    )
    store.append(
        "generation",
        "generation:r:1",
        {
            "research_run_id": "r",
            "generation": 1,
            "status": "COMPLETED",
            "attempt_id": "one",
            "duplicate_skipped": 0,
        },
    )
    store.append("end", "end:r", {"research_run_id": "r", "status": "COMPLETED"})
    item = research_trial_inventory((state,))
    assert item["candidate_evaluation_instances"] == 2
    assert item["unique_candidate_hashes_global"] == 2
    assert item["unique_semantic_strategy_hashes_global"] == 1
    assert item["missing_semantic_hash_instances"] == 0
    assert item["scopes"][0]["unique_semantic_strategy_hashes"] == 1


def test_legacy_candidates_do_not_generate_inferred_semantics(tmp_path: Path) -> None:
    _run(tmp_path, "legacy")
    report = research_trial_inventory((tmp_path,))
    assert report["unique_semantic_strategy_hashes_global"] is None
    assert report["missing_semantic_hash_instances"] == 2


def _measured_dependence(*, count: int = 2, rank: float = 1.5) -> dict[str, object]:
    return {
        "status": "ESTIMATED_TRAIN_ONLY_COHORT",
        "candidate_count": count,
        "return_observations": 42,
        "effective_rank": rank,
        "average_absolute_correlation": 0.42,
        "observed_sharpe_dispersion": 0.015,
        "method": "CORRELATION_ENTROPY_EFFECTIVE_RANK",
        "dsr_calibrated": False,
        "training_cutoff_at": "2025-06-30T00:00:00+00:00",
        "reason": "descriptive cohort dimension, not DSR calibrated",
    }


def test_inventory_shows_cohort_proxy_without_promoting_to_global_dsr(
    tmp_path: Path,
) -> None:
    _run(tmp_path / "first", "one", dependence=_measured_dependence())
    _run(tmp_path / "second", "two", dependence=_measured_dependence(rank=1.2))
    overview = research_trial_inventory((tmp_path / "first", tmp_path / "second"))
    assert overview["trial_dependence_estimated_cohorts"] == 2
    assert overview["trial_dependence_unmeasured_cohorts"] == 0
    assert overview["trial_dependence_scope"] == "TRAIN_ONLY_COHORT_NOT_GLOBAL_DSR"
    ranks = [
        detail["effective_rank_estimate"]
        for detail in overview["trial_dependence_diagnostics_sample"]
    ]
    assert ranks == [1.5, 1.2]
    assert all(
        entry["dsr_calibrated"] is False
        for entry in overview["trial_dependence_diagnostics_sample"]
    )
    assert overview["effective_independent_trials"] is None
    assert overview["history_complete"] is False
    assert "return_series" not in str(overview)


def test_invalid_empirical_cohort_evidence_fails_closed(tmp_path: Path) -> None:
    _run(tmp_path, "bad", dependence=_measured_dependence(rank=22))
    with pytest.raises(EvidenceIntegrityError, match="invalid empirical trial dependence"):
        research_trial_inventory((tmp_path,))


def test_legacy_cohorts_have_no_imputed_correlation(tmp_path: Path) -> None:
    _run(tmp_path, "legacy")
    report = research_trial_inventory((tmp_path,))
    assert report["trial_dependence_estimated_cohorts"] == 0
    assert report["trial_dependence_unmeasured_cohorts"] == 1
    assert report["trial_dependence_diagnostics_sample"] == []
    assert report["effective_independent_trials"] is None
