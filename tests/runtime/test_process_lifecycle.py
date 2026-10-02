from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest

import runtime.process_lifecycle as lifecycle_module
from runtime.process_lifecycle import (
    process_matches,
    spawn_managed_process,
    terminate_process_tree,
)


def test_process_matches_retries_transient_missing_command_line(monkeypatch) -> None:
    calls = 0
    sleeps: list[float] = []

    def command_line(pid: int) -> str | None:
        nonlocal calls
        calls += 1
        if calls < 3:
            return None
        return "python -m runtime.system_worker --managed-run-id run-1"

    monkeypatch.setattr(lifecycle_module, "_command_line", command_line)
    monkeypatch.setattr(lifecycle_module.time, "sleep", sleeps.append)

    assert process_matches(
        123,
        ("runtime.system_worker", "--managed-run-id", "run-1"),
        startup_retries=4,
        retry_delay_seconds=0.02,
    )
    assert calls == 3
    assert sleeps == [0.02, 0.02]


def test_process_matches_does_not_retry_wrong_identity(monkeypatch) -> None:
    calls = 0

    def command_line(pid: int) -> str | None:
        nonlocal calls
        calls += 1
        return "python unrelated-process"

    monkeypatch.setattr(lifecycle_module, "_command_line", command_line)

    assert process_matches(123, ("owned-marker",), startup_retries=4) is False
    assert calls == 1


def test_posix_termination_falls_back_to_pid_when_killpg_is_unavailable(
    monkeypatch,
) -> None:
    calls: list[tuple[int, signal.Signals]] = []
    monkeypatch.delattr(lifecycle_module.os, "killpg", raising=False)
    monkeypatch.setattr(
        lifecycle_module.os,
        "kill",
        lambda pid, sig: calls.append((pid, sig)),
    )

    assert lifecycle_module._terminate_posix(12345) is True
    assert calls == [(12345, signal.SIGTERM)]


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
