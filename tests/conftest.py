from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("FINANCE_AUTORESEARCH_ENV_FILE", "")


@pytest.fixture
def repository_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root
