"""Exclusive, opt-in SDK coordinator lock outside canonical academic ledgers.

An OS-process lock coordinates one local dispatcher.  It does not replace
Quant's server-side checkpoint/token/idempotency checks and does not make a
native ChatGPT model host available; production multi-host leases remain gated.
"""

from __future__ import annotations

import fcntl
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class BusySDKRun(RuntimeError):
    """Another local SDK coordinator holds the same session lock."""


@contextmanager
def scoped_sdk_run_lease(state_dir: Path, session_id: str) -> Iterator[dict[str, Any]]:
    if re.fullmatch(r"[a-f0-9]{32}", session_id) is None:
        raise ValueError("session identifier must be exactly 32 lower-case hex chars")
    if state_dir.is_symlink():
        raise ValueError("state directory symlink refused")
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_dir = state_dir / "sdk-control-locks"
    if lock_dir.is_symlink():
        raise ValueError("lock directory symlink refused")
    lock_dir.mkdir(exist_ok=True)
    lock_path = lock_dir / f"{session_id}.lock"
    if lock_path.is_symlink():
        raise ValueError("lock path symlink refused")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BusySDKRun("another SDK coordinator is running this exact session") from exc
        try:
            yield {
                "schema": "sdk-quant-local-lease-v1",
                "session_id": session_id,
                "mode": "NONBLOCKING_PROCESS_LOCAL_FLOCK",
                "host_distributed_proof": False,
                "orders_enabled": False,
            }
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
