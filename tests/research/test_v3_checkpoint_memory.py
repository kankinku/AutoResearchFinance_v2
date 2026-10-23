"""V3 sidecar advisory in an authenticated checkpoint (opt-in only)."""

import sqlite3

import pytest

from research.llm.v3_parent_sidecar import (
    ResearchParentSidecar,
    SidecarIntegrityError,
)
from tests.research.test_v3_parent_sidecar import DATA, SOURCE, store, trial


def test_readonly_memory_reconciles_negative_candidates_without_creating_db(tmp_path):
    ledger, label = store(tmp_path)
    ledger.record_candidate(label, trial(number=1))
    ledger.record_candidate(label, trial(number=2, risk=True, duplicate=(192,)))
    previous = ledger.audit(label)
    memory = ResearchParentSidecar.read_verified_summary(
        ledger.path,
        label,
        dataset_hash=DATA,
        known_ancestor_hashes=(SOURCE,),
    )
    assert memory["schema"] == "v3-checkpoint-research-memory-v1"
    assert memory["attempt_count"] == 2
    assert memory["decisions"]["REJECT_RISK"] == 1
    assert memory["decisions"]["REJECT_ECONOMIC_DUPLICATE"] == 1
    assert memory["last_event_hash"] == previous["last_event_hash"]
    assert memory["selected_parent_hash"] == previous["selected_parent_hash"]
    assert memory["origin"] == "SCRIPTED_NOT_GPT"
    assert memory["model_autonomy_verified"] is False
    assert memory["official_generation_increment"] == 0
    assert memory["automatic_parent_adoption"] is False
    assert not list(tmp_path.glob("*wal*"))
    assert not list(tmp_path.glob("*shm*"))


def test_memory_does_not_accept_unknown_data_or_ancestry(tmp_path):
    ledger, label = store(tmp_path)
    ledger.record_candidate(label, trial())
    with pytest.raises(SidecarIntegrityError, match="dataset"):
        ResearchParentSidecar.read_verified_summary(
            ledger.path,
            label,
            dataset_hash="9" * 64,
            known_ancestor_hashes=(SOURCE,),
        )
    with pytest.raises(SidecarIntegrityError, match="ancestor"):
        ResearchParentSidecar.read_verified_summary(
            ledger.path,
            label,
            dataset_hash=DATA,
            known_ancestor_hashes=("8" * 64,),
        )
    with pytest.raises(SidecarIntegrityError, match="missing"):
        ResearchParentSidecar.read_verified_summary(
            tmp_path / "absent.sqlite",
            label,
            dataset_hash=DATA,
            known_ancestor_hashes=(SOURCE,),
        )
    assert not (tmp_path / "absent.sqlite").exists()


def test_readonly_memory_detects_corrupt_receipt(tmp_path):
    ledger, label = store(tmp_path)
    ledger.record_candidate(label, trial())
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE candidate_events SET event_json='{}' WHERE sequence=1")
    with pytest.raises(SidecarIntegrityError, match="chain"):
        ResearchParentSidecar.read_verified_summary(
            ledger.path,
            label,
            dataset_hash=DATA,
            known_ancestor_hashes=(SOURCE,),
        )
