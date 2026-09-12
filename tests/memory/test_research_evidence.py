from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from memory.research_evidence import compare_runs, research_evidence


def seed_run(store: EvidenceStore, run_id: str, key: str = "same") -> None:
    store.append(
        "run",
        f"run:{run_id}",
        {
            "research_run_id": run_id,
            "requested_generations": 2,
            "seed": 7,
        },
    )
    store.append(
        "manifest",
        f"manifest:{run_id}",
        {
            "research_run_id": run_id,
            "comparison_key": key,
        },
    )


def attempt(store: EvidenceStore, run_id: str, attempt_id: str, generation: int = 1) -> None:
    store.append(
        "attempt",
        f"attempt:{attempt_id}",
        {
            "research_run_id": run_id,
            "attempt_id": attempt_id,
            "generation": generation,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "candidate",
                    "family": "trend",
                    "status": "REJECT",
                    "failed_gates": ["robustness"],
                    "score": 0.2,
                    "full_cagr": 0.1,
                    "validation_evaluated": False,
                    "validation_passed": None,
                }
            ],
        },
    )


def finish(store: EvidenceStore, run_id: str, attempt_id: str, generation: int = 1) -> None:
    store.append(
        "generation",
        f"generation:{run_id}:{generation}",
        {
            "research_run_id": run_id,
            "generation": generation,
            "attempt_id": attempt_id,
            "status": "FALLBACK",
        },
    )


def test_isolates_runs_and_counts_only_final_attempts(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    for run_id in ("a", "b"):
        seed_run(store, run_id)
        attempt(store, run_id, run_id + "-repair")
        attempt(store, run_id, run_id + "-fallback")
        finish(store, run_id, run_id + "-fallback")
    payload = research_evidence(tmp_path)
    assert len(payload["runs"]) == 2
    for run in payload["runs"]:
        assert run["completed_generations"] == 1
        assert run["candidate_count"] == 1
        assert run["all_attempt_candidate_count"] == 2
        assert run["fallback_rate"] == 1.0
        assert run["pass_rate"] == 0.0
        assert run["validation_survival"]["value"] is None
    assert payload["sealed_oos_survival"]["status"] == "NOT_MEASURED"
    assert len(research_evidence(tmp_path, "a")["runs"]) == 1


def test_journal_idempotency_conflict_and_immutable_rows(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    seed_run(store, "a")
    attempt(store, "a", "x")
    attempt(store, "a", "x")
    assert len(store.events()) == 3
    with pytest.raises(EvidenceIntegrityError, match="conflict"):
        store.append("attempt", "attempt:x", {"research_run_id": "a"})
    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM events")
    assert len(store.events()) == 3


def test_no_success_for_unfinished_attempt_or_absent_denominator(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    seed_run(store, "a")
    attempt(store, "a", "unfinished")
    run = research_evidence(tmp_path)["runs"][0]
    assert run["completed_generations"] == 0
    assert run["pass_rate"] is None
    assert run["status"] == "INCOMPLETE"
    assert run["candidate_count"] == 0


def test_comparison_rejects_different_manifest_and_missing_run(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    seed_run(store, "a", "one")
    seed_run(store, "b", "two")
    with pytest.raises(ValueError, match="comparison"):
        compare_runs(tmp_path, ["a", "b"])
    with pytest.raises(ValueError, match="missing"):
        compare_runs(tmp_path, ["a", "missing"])


def test_legacy_not_merged_and_reads_do_not_create_state(tmp_path: Path) -> None:
    state = tmp_path / "absent"
    assert research_evidence(state)["status"] == "EMPTY"
    assert not state.exists()
    tmp_path.joinpath("test-records.jsonl").write_text(
        json.dumps({"generation": 1, "status": "SURVIVOR"}) + "\n", encoding="utf-8"
    )
    payload = research_evidence(tmp_path)
    assert payload["runs"] == []
    assert payload["legacy"] == {"status": "LEGACY_UNSCOPED", "record_count": 1}


def test_damaged_database_fails_closed(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_bytes(b"interrupted database write")
    with pytest.raises(EvidenceIntegrityError):
        research_evidence(tmp_path)


def test_repeated_failures_and_generation_curve(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    seed_run(store, "a")
    for generation in (1, 2):
        attempt(store, "a", str(generation), generation)
        finish(store, "a", str(generation), generation)
    run = research_evidence(tmp_path)["runs"][0]
    assert run["repeated_failure_rate"] == 0.5
    assert run["unique_candidate_count"] == 1
    assert len(run["generations"]) == 2
    assert run["generations"][0]["best_attempt"]["full_cagr"] == 0.1
    assert run["generations"][0]["best_passed"] is None


def test_invalid_event_shape_and_post_completion_writes_are_rejected(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    seed_run(store, "a")
    with pytest.raises(EvidenceIntegrityError):
        store.append("attempt", "bad", {"research_run_id": "a"})
    store.append("end", "end:a", {"research_run_id": "a", "status": "FAILED"})
    with pytest.raises(EvidenceIntegrityError, match="closed"):
        attempt(store, "a", "late")


def test_projection_recovers_after_interrupted_replace_without_losing_legacy(
    tmp_path: Path, monkeypatch
) -> None:
    import memory.evidence_knowledge as knowledge

    store = EvidenceStore(tmp_path)
    seed_run(store, "a")
    attempt(store, "a", "x")
    target = tmp_path / "knowledge.json"
    prior = {"schema_version": 8, "known_good": [{"old": True}], "extension": 42}
    target.write_text(json.dumps(prior), encoding="utf-8")
    replace = knowledge.os.replace

    def interrupted(*args):
        raise OSError("simulated power loss")

    monkeypatch.setattr(knowledge.os, "replace", interrupted)
    with pytest.raises(EvidenceIntegrityError):
        knowledge.sync_knowledge(tmp_path)
    assert json.loads(target.read_text(encoding="utf-8")) == prior
    monkeypatch.setattr(knowledge.os, "replace", replace)
    knowledge.sync_knowledge(tmp_path)
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result["extension"] == 42 and result["schema_version"] == 8
    assert len(result["known_bad"]) == 1


def test_digest_detects_changed_kind_and_uncommitted_write_is_absent(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    seed_run(store, "a")
    with sqlite3.connect(store.path) as conn:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT INTO events(id,kind,payload,checksum) VALUES('partial','end','{}','x')"
        )
        conn.rollback()
    assert len(store.events()) == 2
    with sqlite3.connect(store.path) as conn:
        conn.execute("DROP TRIGGER prevent_update")
        conn.execute("UPDATE events SET kind='attempt' WHERE kind='manifest'")
    with pytest.raises(EvidenceIntegrityError):
        store.events()


def test_completed_run_requires_all_final_generations(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    seed_run(store, "a")
    store.append("end", "end:a", {"research_run_id": "a", "status": "COMPLETED"})
    with pytest.raises(EvidenceIntegrityError):
        research_evidence(tmp_path)


def test_validation_survival_uses_only_evaluated_candidates(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    seed_run(store, "a")
    rows = [
        {
            "candidate_hash": str(i),
            "family": "trend",
            "status": "REJECT",
            "failed_gates": ["robustness"],
            "validation_evaluated": measured,
            "validation_passed": passed,
        }
        for i, (measured, passed) in enumerate([(True, True), (True, False), (False, None)])
    ]
    store.append(
        "attempt",
        "attempt:x",
        {
            "research_run_id": "a",
            "attempt_id": "x",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": rows,
        },
    )
    finish(store, "a", "x")
    assert research_evidence(tmp_path)["runs"][0]["validation_survival"]["value"] == 0.5


def test_failure_context_groups_repetition_without_mixing_conditions(tmp_path: Path) -> None:
    from memory.evidence_knowledge import failure_context

    store = EvidenceStore(tmp_path)
    seed_run(store, "a", "condition-a")
    for generation in (1, 2):
        attempt(store, "a", str(generation), generation)
    seed_run(store, "b", "condition-b")
    attempt(store, "b", "other")
    rows = failure_context(tmp_path)
    assert len(rows) == 2
    assert {r["comparison_key"]: r["occurrences"] for r in rows} == {
        "condition-a": 2,
        "condition-b": 1,
    }
    assert len(failure_context(tmp_path, max_items=1)) == 1


def test_validation_scope_comes_from_manifest_zone(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.append("run", "run:a", {"research_run_id": "a", "requested_generations": 1, "seed": 0})
    store.append(
        "manifest",
        "manifest:a",
        {
            "research_run_id": "a",
            "comparison_key": "test",
            "data_zone": "validation",
        },
    )
    assert research_evidence(tmp_path)["runs"][0]["validation_survival"]["scope"] == (
        "validation_walk_forward"
    )
