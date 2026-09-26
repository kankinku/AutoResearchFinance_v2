from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

_LOCAL_LOCK = threading.Lock()


class LifecycleBusyError(RuntimeError):
    """Raised when another process is changing managed-system lifecycle state."""


@contextmanager
def lifecycle_lock(path: Path) -> Iterator[None]:
    """Acquire a nonblocking cross-process lock for start/stop transitions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if not _LOCAL_LOCK.acquire(blocking=False):
        raise LifecycleBusyError("managed system lifecycle is busy")
    handle: BinaryIO | None = None
    try:
        handle = path.open("a+b")
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        _lock(handle)
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        if handle is not None:
            handle.close()
        _LOCAL_LOCK.release()


def _lock(handle: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise LifecycleBusyError("managed system lifecycle is busy") from exc
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise LifecycleBusyError("managed system lifecycle is busy") from exc


def _unlock(handle: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            return
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        return
