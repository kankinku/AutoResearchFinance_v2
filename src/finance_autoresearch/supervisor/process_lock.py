from __future__ import annotations

import ctypes
import json
import os
import time
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

if os.name == "nt":
    from ctypes import wintypes

    _ERROR_ACCESS_DENIED = 5
    _ERROR_INVALID_PARAMETER = 87
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _OPEN_PROCESS = _KERNEL32.OpenProcess
    _OPEN_PROCESS.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    _OPEN_PROCESS.restype = wintypes.HANDLE

    _GET_EXIT_CODE_PROCESS = _KERNEL32.GetExitCodeProcess
    _GET_EXIT_CODE_PROCESS.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    )
    _GET_EXIT_CODE_PROCESS.restype = wintypes.BOOL

    _CLOSE_HANDLE = _KERNEL32.CloseHandle
    _CLOSE_HANDLE.argtypes = (wintypes.HANDLE,)
    _CLOSE_HANDLE.restype = wintypes.BOOL


class ProcessLockTimeoutError(TimeoutError):
    pass


class ProcessLock(AbstractContextManager[None]):
    def __init__(
        self,
        lock_path: Path | None = None,
        *,
        timeout_seconds: float = 5.0,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        self._lock_path = lock_path
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._thread_lock = RLock()
        self._fd: int | None = None

    @classmethod
    def for_state_store(cls, state_store: object) -> "ProcessLock":
        db_path = getattr(state_store, "_db_path", None)
        project_id = getattr(state_store, "_project_id", "project")
        if isinstance(db_path, Path):
            lock_path = db_path.with_name(
                f"{db_path.name}.{project_id}.supervisor.lock"
            )
            return cls(lock_path=lock_path)
        return cls()

    def __enter__(self) -> None:
        self.acquire()
        return None

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.release()
        return False

    def acquire(self) -> None:
        self._thread_lock.acquire()
        if self._lock_path is None:
            return

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            try:
                self._fd = os.open(
                    str(self._lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_RDWR,
                )
                self._write_owner_metadata()
                return
            except FileExistsError as exc:
                if self._should_reclaim_stale_lock():
                    try:
                        self._lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    self._thread_lock.release()
                    raise ProcessLockTimeoutError(
                        f"timed out acquiring process lock: {self._lock_path}"
                    ) from exc
                time.sleep(self._poll_interval_seconds)

    def release(self) -> None:
        try:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
                self._unlink_lock_file()
        finally:
            try:
                self._thread_lock.release()
            except RuntimeError:
                pass

    def _write_owner_metadata(self) -> None:
        if self._fd is None:
            return
        metadata = {
            "pid": os.getpid(),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }
        os.write(self._fd, json.dumps(metadata).encode("utf-8"))
        os.fsync(self._fd)

    def _should_reclaim_stale_lock(self) -> bool:
        if self._lock_path is None or not self._lock_path.exists():
            return False
        try:
            metadata = json.loads(self._lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False

        pid = metadata.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return True
        return not self._is_process_alive(pid)

    def _is_process_alive(self, pid: int) -> bool:
        if os.name == "nt":
            return self._is_process_alive_windows(pid)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _is_process_alive_windows(self, pid: int) -> bool:
        handle = _OPEN_PROCESS(
            _PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        if not handle:
            last_error = ctypes.get_last_error()
            if last_error == _ERROR_INVALID_PARAMETER:
                return False
            return True

        exit_code = wintypes.DWORD()
        try:
            if _GET_EXIT_CODE_PROCESS(handle, ctypes.byref(exit_code)) == 0:
                last_error = ctypes.get_last_error()
                if last_error == _ERROR_INVALID_PARAMETER:
                    return False
                if last_error == _ERROR_ACCESS_DENIED:
                    return True
                return True
            return exit_code.value == _STILL_ACTIVE
        finally:
            _CLOSE_HANDLE(handle)

    def _unlink_lock_file(self) -> None:
        if self._lock_path is None:
            return

        deadline = time.monotonic() + max(self._poll_interval_seconds * 10, 0.5)
        while True:
            try:
                self._lock_path.unlink()
                return
            except FileNotFoundError:
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(self._poll_interval_seconds)
