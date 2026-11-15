"""T15: avoid repeatedly deserializing all events while preserving fail-closed rules."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import memory.evidence_store as evidence_store
from memory.evidence_store import EvidenceIntegrityError, EvidenceStore


def _run(store: EvidenceStore, name: str) -> None:
    store.append("run", f"run:{name}", {
        "research_run_id": name, "requested_generations": 25, "seed": 1,
    })


def _generation(store: EvidenceStore, name: str, number: int) -> None:
    store.append("generation", f"generation:{name}:{number}", {
        "research_run_id": name, "generation": number,
        "status": "FALLBACK", "attempt_id": f"{name}-{number}",
    })


def test_append_checks_existing_run_state_without_full_python_json_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = EvidenceStore(tmp_path)
    _run(store, "first")
    _run(store, "second")
    _generation(store, "first", 1)

    class DumpOnlyJSON:
        dumps = staticmethod(json.dumps)

        @staticmethod
        def loads(_text: str) -> object:
            raise AssertionError("append must not decode entire event history")

    # A reader still uses json.loads and the canonical checksum; only append
    # should avoid decoding every unrelated event in the history.
    with monkeypatch.context() as patch:
        patch.setattr(evidence_store, "json", DumpOnlyJSON)
        _generation(store, "second", 1)
    assert [x["payload"]["research_run_id"] for x in store.events()] == [
        "first", "second", "first", "second",
    ]


@pytest.mark.parametrize("broken", [
    '{"generation": 5}',
    '["wrong-object-type"]',
    '{"research_run_id": 100}',
    '{"research_run_id": ',
])
def test_legacy_corrupt_history_fails_closed_before_any_append(
    tmp_path: Path, broken: str,
) -> None:
    store = EvidenceStore(tmp_path)
    _run(store, "current")
    with sqlite3.connect(store.path) as connection:
        # The expression index itself prevents syntactically malformed JSON.
        if broken == '{"research_run_id": ':
            with pytest.raises(sqlite3.OperationalError, match="malformed JSON"):
                connection.execute(
                    "INSERT INTO events(id,kind,payload,checksum) VALUES(?,?,?,?)",
                    ("legacy-corrupt", "generation", broken, "broken-checksum"),
                )
            assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 1
            return
        # Syntactically valid JSON without a string run ID still fails closed.
        connection.execute(
            "INSERT INTO events(id,kind,payload,checksum) VALUES(?,?,?,?)",
            ("legacy-corrupt", "generation", broken, "broken-checksum"),
        )
    with pytest.raises(EvidenceIntegrityError):
        _generation(store, "current", 1)
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 2


def test_interleaved_two_run_closure_does_not_lock_unrelated_run(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    _run(store, "a")
    _run(store, "b")
    store.append("end", "end:a", {"research_run_id": "a", "status": "FAILED"})
    _generation(store, "b", 1)
    with pytest.raises(EvidenceIntegrityError, match="closed"):
        _generation(store, "a", 1)
    assert len(store.events()) == 4
    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE events SET kind='run' WHERE id='end:a'")
    assert len(store.events()) == 4


def test_existing_run_lookup_has_an_index_without_overwriting_old_rows(
    tmp_path: Path,
) -> None:
    store = EvidenceStore(tmp_path)
    _run(store, "a")
    _run(store, "b")
    _generation(store, "a", 1)
    before = store.events()
    with sqlite3.connect(store.path) as connection:
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('events')")
        }
        assert "idx_events_run_identity" in indexes
        query_plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT kind FROM events "
            "WHERE json_type(payload, '$.research_run_id')='text' "
            "AND json_extract(payload, '$.research_run_id')=? "
            "AND kind IN ('run','manifest','end')",
            ("a",),
        ).fetchall()
        assert any("idx_events_run_identity" in row[3] for row in query_plan)
    _generation(store, "b", 1)
    assert store.events()[: len(before)] == before


def test_missing_foreign_run_identity_after_index_creation_still_blocks_append(
    tmp_path: Path,
) -> None:
    store = EvidenceStore(tmp_path)
    _run(store, "a")
    with sqlite3.connect(store.path) as connection:
        # Even a JSON object with no research_run_id must not be silently
        # excluded from an indexed run-specific query.
        connection.execute(
            "INSERT INTO events(id,kind,payload,checksum) VALUES(?,?,?,?)",
            ("bad:unscoped", "generation", '{"generation":2}', "tampered"),
        )
    with pytest.raises(EvidenceIntegrityError):
        _generation(store, "a", 1)


def test_index_migration_fails_closed_on_preexisting_malformed_json(
    tmp_path: Path,
) -> None:
    store = EvidenceStore(tmp_path)
    _run(store, "a")
    # Model an old valid-schema database with no expression index.
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP INDEX idx_events_run_identity")
        connection.execute(
            "INSERT INTO events(id,kind,payload,checksum) VALUES(?,?,?,?)",
            ("legacy:broken", "generation", '{"research_run_id": ', "broken"),
        )
    with pytest.raises(EvidenceIntegrityError):
        _generation(store, "a", 1)
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 2
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        triggers = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )}
        assert {"prevent_update", "prevent_delete"} <= triggers


def test_existing_index_rejects_invalid_json_on_any_run(
    tmp_path: Path,
) -> None:
    store = EvidenceStore(tmp_path)
    _run(store, "a")
    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.OperationalError, match="malformed JSON"):
            connection.execute(
                "INSERT INTO events(id,kind,payload,checksum) VALUES(?,?,?,?)",
                ("other:broken", "generation", '{"research_run_id": ', "invalid"),
            )
    _generation(store, "a", 1)
    assert len(store.events()) == 2


def test_valid_legacy_ledger_gains_index_without_changing_old_evidence(
    tmp_path: Path,
) -> None:
    store = EvidenceStore(tmp_path)
    _run(store, "legacy")
    _generation(store, "legacy", 1)
    _generation(store, "legacy", 2)
    before = store.events()
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP INDEX idx_events_run_identity")
        count_before = connection.execute("SELECT count(*) FROM events").fetchone()[0]
        trigger_sql_before = list(connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
        ))
    _generation(store, "legacy", 3)
    after = store.events()
    assert after[:-1] == before
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == count_before + 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert trigger_sql_before == list(connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"
        ))
        assert "idx_events_run_identity" in {
            item[1] for item in connection.execute("PRAGMA index_list(events)")
        }


def test_two_concurrent_first_appends_create_one_safe_index(
    tmp_path: Path,
) -> None:
    import threading

    store = EvidenceStore(tmp_path)
    _run(store, "legacy")
    with sqlite3.connect(store.path) as conn:
        conn.execute("DROP INDEX idx_events_run_identity")
    barrier = threading.Barrier(3)
    errors = []

    def worker(n: int) -> None:
        try:
            barrier.wait(timeout=3)
            _generation(store, "legacy", n)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in (1, 2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=3)
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()
    assert not errors, errors
    assert len(store.events()) == 3
    with sqlite3.connect(store.path) as conn:
        names = [
            x[1] for x in conn.execute("PRAGMA index_list(events)")
            if x[1] == "idx_events_run_identity"
        ]
        assert names == ["idx_events_run_identity"]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_evidence_performance_receipts_verify_after_json_roundtrip() -> None:
    from core.integrity.hashes import content_hash

    repository = Path(__file__).resolve().parents[2]
    root = repository / "docs" / "operations"
    variants = (
        "baseline", "baseline-repeat", "optimized", "indexed",
        "final-optimized", "final-repeat",
    )
    receipts = {}
    for variant in variants:
        receipt = json.loads(
            (root / f"quant-t15-evidence-scaling-{variant}-20261110.json")
            .read_text(encoding="utf-8")
        )
        assert receipt["result_hash"] == content_hash({
            key: value for key, value in receipt.items() if key != "result_hash"
        })
        assert receipt["fixture"]["source"] == "SYNTHETIC_NOT_EXISTING_G150_OR_LIVE_MARKET"
        assert receipt["predeclared_thresholds_ms"]["10000"]["append"] == 100
        receipts[variant] = receipt
    assert (
        receipts["baseline"]["sizes"]["10000"]["thresholds_passed"]["append_p95"]
        is False
    )
    assert all(
        receipts[k]["sizes"]["10000"]["thresholds_passed"]["append_p95"] is True
        for k in ("final-optimized", "final-repeat")
    )
