from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root
