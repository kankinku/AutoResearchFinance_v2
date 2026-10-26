"""SDK generation lease is isolated and never edits Quant's canonical journal."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from application.sdk_quant_run_lease import BusySDKRun, scoped_sdk_run_lease

SID = "f" * 32


def test_second_runner_same_session_blocks_then_releases(tmp_path: Path):
    root = tmp_path / "quant-isolated-state"
    with scoped_sdk_run_lease(root, SID) as proof:
        assert proof["session_id"] == SID
        assert proof["mode"] == "NONBLOCKING_PROCESS_LOCAL_FLOCK"
        with pytest.raises(BusySDKRun):
            with scoped_sdk_run_lease(root, SID):
                pytest.fail("duplicate runner acquired the lock")
    with scoped_sdk_run_lease(root, SID):
        pass
    assert not (root / "academic-gpt-checkpoints" / "cycles.sqlite").exists()


def test_process_exit_frees_lease(tmp_path: Path):
    root = tmp_path / "quant-isolated-state"
    code = (
        "from pathlib import Path\nfrom application.sdk_quant_run_lease "
        "import scoped_sdk_run_lease\n"
        f"with scoped_sdk_run_lease(Path({str(root)!r}), {SID!r}):\n"
        "    print('locked')\n"
    )
    # A normal / unexpected process exit must not retain an indefinite lock.
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert "locked" in result.stdout
    with scoped_sdk_run_lease(root, SID):
        pass


def test_different_session_can_acquire_separately(tmp_path: Path):
    with scoped_sdk_run_lease(tmp_path, SID):
        with scoped_sdk_run_lease(tmp_path, "a" * 32):
            pass


def test_invalid_session_and_existing_symlink_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="session"):
        with scoped_sdk_run_lease(tmp_path, "../../escape"):
            pass
    target = tmp_path / "elsewhere"
    target.mkdir()
    (tmp_path / "sdk-control-locks").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        with scoped_sdk_run_lease(tmp_path, SID):
            pass
