"""T4 gate keeps original SQLite state out of any copied-data write path."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.t4_shadow_checkpoint_smoke import (
    ShadowCheckpointError,
    _clone_db,
    shadow_checkpoint,
)


def test_sqlite_copy_is_independent_and_original_is_read_only(tmp_path: Path) -> None:
    original = tmp_path / "original.sqlite"
    secondary = tmp_path / "clone.sqlite"
    with sqlite3.connect(original) as db:
        db.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO sample (value) VALUES ('immutable-original')")
    _clone_db(original, secondary)
    with sqlite3.connect(secondary) as db:
        db.execute("UPDATE sample SET value='changed-only-in-copy' WHERE id=1")
        assert db.execute("SELECT value FROM sample").fetchone()[0] == "changed-only-in-copy"
    with sqlite3.connect(original) as db:
        assert db.execute("SELECT value FROM sample").fetchone()[0] == "immutable-original"
    with pytest.raises(ShadowCheckpointError, match="already exists"):
        _clone_db(original, secondary)
    with pytest.raises(ShadowCheckpointError, match="snapshot missing"):
        _clone_db(tmp_path / "not-a-file.sqlite", tmp_path / "new.sqlite")


def test_missing_source_or_bad_session_fails_before_clone(tmp_path: Path) -> None:
    with pytest.raises(ShadowCheckpointError, match="snapshot"):
        shadow_checkpoint(
            project_root=tmp_path, snapshot=tmp_path, session_id="a" * 32, expected_generations=79
        )
    empty = tmp_path / "snapshot"
    empty.mkdir()
    with pytest.raises(ShadowCheckpointError, match="identity"):
        shadow_checkpoint(
            project_root=tmp_path, snapshot=empty, session_id="bad", expected_generations=79
        )
