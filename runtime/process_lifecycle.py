from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path


def spawn_managed_process(
    command: list[str],
    cwd: Path,
) -> subprocess.Popen[bytes]:
    if sys.platform == "win32":
        return subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def process_matches(
    pid: int,
    markers: Sequence[str],
    *,
    startup_retries: int = 4,
    retry_delay_seconds: float = 0.01,
) -> bool:
    if pid <= 0:
        return False
    if startup_retries < 0:
        raise ValueError("startup_retries cannot be negative")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative")

    for attempt in range(startup_retries + 1):
        command_line = _command_line(pid)
        if command_line is not None:
            return all(marker in command_line for marker in markers if marker)
        if attempt < startup_retries:
            time.sleep(retry_delay_seconds)
    return False


def terminate_process_tree(pid: int, markers: Sequence[str]) -> bool:
    if not process_matches(pid, markers):
        return False
    if sys.platform == "win32":
        return _terminate_windows(pid)
    return _terminate_posix(pid)


def _command_line(pid: int) -> str | None:
    if sys.platform == "win32":
        return _windows_command_line(pid)
    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = proc_cmdline.read_bytes()
    except OSError:
        raw = b""
    if raw:
        return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    command_line = completed.stdout.strip()
    return command_line if completed.returncode == 0 and command_line else None


def _windows_command_line(pid: int) -> str | None:
    script = (
        "$p=Get-CimInstance Win32_Process -Filter \"ProcessId = "
        f"{pid}\" -ErrorAction SilentlyContinue;"
        "if ($null -eq $p) { exit 3 };"
        "[Console]::Out.Write($p.CommandLine)"
    )
    for executable in ("powershell.exe", "pwsh.exe"):
        try:
            completed = subprocess.run(
                [
                    executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()
        if completed.returncode == 3:
            return None
    return None


def _terminate_windows(pid: int) -> bool:
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _terminate_posix(pid: int) -> bool:
    try:
        os.killpg(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return True
        except OSError:
            return False
