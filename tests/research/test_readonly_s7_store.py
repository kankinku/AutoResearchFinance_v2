"""M1: actual gateway S7 evidence is read without a write-capable SQLite connection."""

from __future__ import annotations

import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from application.research_handoff_builder import build_research_handoff
from application.research_s7_readonly import EvidenceReadError, read_committed_s7
from tests.research.test_evidence_handoff_m0 import _history_fixture


def test_reads_validated_gateway_s7_and_never_changes_sqlite(tmp_path: Path):
    server, state, receipts = _history_fixture(tmp_path)
    dbdir = tmp_path / "state" / "academic-gpt-checkpoints"
    dbfiles = (dbdir / "gateway.sqlite", dbdir / "cycles.sqlite")
    with sqlite3.connect(dbfiles[0]) as db:
        total = db.execute("SELECT count(*) FROM experiment_reports").fetchone()[0]
    actual = read_committed_s7(dbdir, state)
    assert actual == receipts
    assert build_research_handoff(state, actual)["completed_generations"] == 2
    with sqlite3.connect(dbfiles[0]) as db:
        assert db.execute("SELECT count(*) FROM experiment_reports").fetchone()[0] == total


def test_missing_stored_s7_is_not_recomputed(tmp_path: Path):
    _, state, _ = _history_fixture(tmp_path)
    dbdir = tmp_path / "state" / "academic-gpt-checkpoints"
    with sqlite3.connect(dbdir / "gateway.sqlite") as db:
        db.execute("DELETE FROM experiment_reports WHERE generation=2")
    with pytest.raises(EvidenceReadError, match="missing"):
        read_committed_s7(dbdir, state)
    with sqlite3.connect(dbdir / "gateway.sqlite") as db:
        assert db.execute("SELECT count(*) FROM experiment_reports").fetchone()[0] == 1


def test_stale_snapshot_or_corrupt_stored_digest_rejected(tmp_path: Path):
    _, state, _ = _history_fixture(tmp_path)
    dbdir = tmp_path / "state" / "academic-gpt-checkpoints"
    altered = deepcopy(state)
    altered["history"][-1]["metrics"]["total_return"] = 42.0
    with pytest.raises(EvidenceReadError, match="snapshot|canonical"):
        read_committed_s7(dbdir, altered)
    with sqlite3.connect(dbdir / "gateway.sqlite") as db:
        db.execute("UPDATE experiment_reports SET report_hash=? WHERE generation=1", ("f" * 64,))
    with pytest.raises(EvidenceReadError, match="S7"):
        read_committed_s7(dbdir, state)


def test_symlinked_db_and_missing_or_other_session_block(tmp_path: Path):
    _, state, _ = _history_fixture(tmp_path)
    dbdir = tmp_path / "state" / "academic-gpt-checkpoints"
    other = deepcopy(state)
    other["session_id"] = "f" * 32
    with pytest.raises(EvidenceReadError, match="session|snapshot"):
        read_committed_s7(dbdir, other)
    direct = dbdir / "gateway.sqlite"
    real = dbdir / "raw-copy.sqlite"
    direct.rename(real)
    direct.symlink_to(real)
    with pytest.raises(EvidenceReadError, match="symlink"):
        read_committed_s7(dbdir, state)


def test_readonly_bundle_can_rebuild_from_two_existing_canonical_databases(tmp_path: Path):
    from application.research_s7_readonly import read_research_bundle_readonly

    _, source, receipts = _history_fixture(tmp_path)
    root = tmp_path / "state" / "academic-gpt-checkpoints"
    bundle = read_research_bundle_readonly(root, source["session_id"])
    assert bundle["snapshot"]["history"] == source["history"]
    assert bundle["receipts"] == receipts
    assert not any("token" in k for k in bundle["snapshot"])
    assert build_research_handoff(
        **{"snapshot": bundle["snapshot"], "s7_receipts": bundle["receipts"]}
    )
    assert bundle["snapshot"]["orders_enabled"] is False


def test_readonly_bundle_rejects_unrecognised_session(tmp_path: Path):
    from application.research_s7_readonly import read_research_bundle_readonly

    _, source, receipts = _history_fixture(tmp_path)
    root = tmp_path / "state" / "academic-gpt-checkpoints"
    with pytest.raises(EvidenceReadError, match="session"):
        read_research_bundle_readonly(root, "0" * 32)
