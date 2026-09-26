from __future__ import annotations

import sys
from pathlib import Path

import pytest

from runtime.process_lifecycle import (
    process_matches,
    spawn_managed_process,
    terminate_process_tree,
)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process lifecycle acceptance")
def test_managed_process_identity_and_tree_termination(tmp_path: Path) -> None:
    marker = "phase3-4-managed-process-marker"
    process = spawn_managed_process(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            marker,
        ],
        tmp_path,
    )
    try:
        assert process_matches(process.pid, (marker,))
        assert not process_matches(process.pid, ("wrong-marker",))
        assert terminate_process_tree(process.pid, (marker,))
        assert process.wait(timeout=5) is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process lifecycle acceptance")
def test_wrong_identity_never_terminates_process(tmp_path: Path) -> None:
    marker = "phase3-4-identity-guard"
    process = spawn_managed_process(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            marker,
        ],
        tmp_path,
    )
    try:
        assert terminate_process_tree(process.pid, ("not-the-owned-process",)) is False
        assert process.poll() is None
    finally:
        terminate_process_tree(process.pid, (marker,))
        process.wait(timeout=5)
