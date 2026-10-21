"""Contract tests for the fixed-cohort operator, using temp SQLite only.

Never creates or extends a real research session.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.run_academic_cohort import atomic_json, perform_backup, run


def test_atomic_manifest_replaces_json(tmp_path: Path) -> None:
    path = tmp_path / "cohort.json"
    atomic_json(path, {"state": "BACKED_UP", "completed": 152})
    atomic_json(path, {"state": "RUNNING", "completed": 153})
    assert json.loads(path.read_text()) == {"state": "RUNNING", "completed": 153}
    assert not (tmp_path / "cohort.json.tmp").exists()


def test_integrity_checked_sqlite_backup(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog.sqlite"):
        with sqlite3.connect(source / name) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE evidence (seq INTEGER PRIMARY KEY, v TEXT NOT NULL)")
            conn.execute("INSERT INTO evidence VALUES (1,'immutable')")
    target = tmp_path / "backup"
    hashes = perform_backup(SimpleNamespace(state=source), target, "a" * 32, 152, 252, "b" * 64)
    assert len(hashes) == 3
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["old_completed"] == 152
    assert manifest["new_target"] == 252
    assert manifest["previous_head"] == "b" * 64
    for name, digest in hashes.items():
        copy = target / name
        assert digest == hashlib.sha256(copy.read_bytes()).hexdigest()
        with sqlite3.connect(copy) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("SELECT v FROM evidence WHERE seq=1").fetchone()[0] == "immutable"
    with pytest.raises(FileExistsError):
        perform_backup(SimpleNamespace(state=source), target, "a" * 32, 152, 252, "b" * 64)


def test_rejects_invalid_ids_and_beyond_g1000() -> None:
    with pytest.raises(ValueError, match="cohort_id"):
        run("../escape", 152, 100)
    with pytest.raises(ValueError, match="upper bound"):
        run("next-100", 952, 100)
    with pytest.raises(ValueError, match="size"):
        run("next-100", 152, 101)


def test_controller_target_is_dynamic() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts/fresh_development_cohort_controller_20261021.py"
    )
    src = path.read_text()
    assert 'target = result["requested_generations"]' in src
    assert 'result["completed_generations"] < target' in src
    assert 'result["requested_generations"] == 152' not in src
