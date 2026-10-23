"""Checkpoint extension backs up exactly the SQLite DBs present in its pinned store."""

from pathlib import Path

import pytest

from scripts.extend_completed_academic_session import checkpoint_backup_sources


def test_current_v2_only_catalog_backup_is_sufficient(tmp_path: Path) -> None:
    for name in ("gateway.sqlite", "cycles.sqlite", "catalog-s6-v2.sqlite"):
        (tmp_path / name).write_bytes(b"SQLite fixture placeholder")
    found = checkpoint_backup_sources(tmp_path)
    assert [p.name for p in found] == [
        "gateway.sqlite",
        "cycles.sqlite",
        "catalog-s6-v2.sqlite",
    ]


def test_prior_optional_catalogs_are_preserved_when_present(tmp_path: Path) -> None:
    for name in (
        "gateway.sqlite",
        "cycles.sqlite",
        "catalog.sqlite",
        "catalog-s6-v1.sqlite",
        "catalog-s6-v2.sqlite",
    ):
        (tmp_path / name).write_bytes(b"SQLite fixture placeholder")
    found = checkpoint_backup_sources(tmp_path)
    assert len(found) == 5
    assert found[-1].name == "catalog-s6-v2.sqlite"


@pytest.mark.parametrize("missing", ["gateway.sqlite", "cycles.sqlite", "catalog-s6-v2.sqlite"])
def test_missing_required_current_backup_files_fail_before_creation(
    tmp_path: Path, missing: str
) -> None:
    for name in ("gateway.sqlite", "cycles.sqlite", "catalog-s6-v2.sqlite"):
        if name != missing:
            (tmp_path / name).write_bytes(b"x")
    with pytest.raises(RuntimeError, match="missing required"):
        checkpoint_backup_sources(tmp_path)
    assert not (tmp_path / "backup").exists()


def test_unknown_catalog_file_never_substitutes_pinned_v2(tmp_path: Path) -> None:
    for name in (
        "gateway.sqlite",
        "cycles.sqlite",
        "catalog-s6-v1.sqlite",
        "catalog-unverified.sqlite",
    ):
        (tmp_path / name).write_bytes(b"x")
    with pytest.raises(RuntimeError, match="catalog-s6-v2"):
        checkpoint_backup_sources(tmp_path)
