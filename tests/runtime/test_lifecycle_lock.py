from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from runtime.lifecycle_lock import LifecycleBusyError, lifecycle_lock


def test_lifecycle_lock_is_nonblocking_within_process(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "system" / "lifecycle.lock"

    with lifecycle_lock(lock_path):
        with pytest.raises(LifecycleBusyError, match="busy"):
            with lifecycle_lock(lock_path):
                raise AssertionError("second lifecycle lock must not be acquired")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX subprocess lock acceptance")
def test_lifecycle_lock_blocks_concurrent_process(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "system" / "lifecycle.lock"
    repo_root = Path(__file__).resolve().parents[2]
    code = (
        "from pathlib import Path;"
        "from runtime.lifecycle_lock import lifecycle_lock;"
        f"p=Path({str(lock_path)!r});"
        "ctx=lifecycle_lock(p);"
        "ctx.__enter__();"
        "print('LOCKED', flush=True);"
        "import time; time.sleep(30)"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "LOCKED"
        with pytest.raises(LifecycleBusyError, match="busy"):
            with lifecycle_lock(lock_path):
                raise AssertionError("concurrent lifecycle lock must not be acquired")
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_lifecycle_lock_releases_after_context_exit(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "system" / "lifecycle.lock"

    with lifecycle_lock(lock_path):
        pass

    with lifecycle_lock(lock_path):
        pass
