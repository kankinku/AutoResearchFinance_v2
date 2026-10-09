"""The code hash must cover modules affecting evaluation or canonical IR."""

from __future__ import annotations

from pathlib import Path

from orchestration.evidence import project_code_hash


def test_shared_foundation_and_memory_change_project_code_hash(tmp_path: Path) -> None:
    (tmp_path / "foundation").mkdir()
    (tmp_path / "memory").mkdir()
    (tmp_path / "foundation" / "hashes.py").write_text("first", encoding="utf-8")
    (tmp_path / "memory" / "frontier.py").write_text("first", encoding="utf-8")
    initial = project_code_hash(tmp_path)
    (tmp_path / "foundation" / "hashes.py").write_text("second", encoding="utf-8")
    assert project_code_hash(tmp_path) != initial
    current = project_code_hash(tmp_path)
    (tmp_path / "memory" / "frontier.py").write_text("second", encoding="utf-8")
    assert project_code_hash(tmp_path) != current


def test_project_dependency_lockfile_changes_code_identity(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'", encoding="utf-8")
    baseline = project_code_hash(tmp_path)
    (tmp_path / "uv.lock").write_text("version=1", encoding="utf-8")
    assert project_code_hash(tmp_path) != baseline
    (tmp_path / "uv.lock").write_text("version=2", encoding="utf-8")
    assert project_code_hash(tmp_path) != baseline
