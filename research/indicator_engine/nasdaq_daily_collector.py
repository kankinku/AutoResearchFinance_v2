"""Operator-invoked daily Nasdaq QQQ capture with integrity-checked idempotency.

A UTC collection date is not a historical publication or point-in-time proof.
No scheduler, trading integration or promotion is provided by this module.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path

from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_append_only_archive import archive_nasdaq_qqq_snapshot
from research.indicator_engine.nasdaq_archive_inventory import audit_nasdaq_qqq_archive
from research.indicator_engine.nasdaq_capture import _http_fetch


def collect_nasdaq_qqq_daily(
    root: Path,
    start: date,
    end: date,
    *,
    at: datetime | None = None,
    fetch_bytes: Callable[[str], bytes] = _http_fetch,
) -> dict[str, object]:
    """Append at most one capture per UTC collection date, with an exclusive lock.

    Audit the *entire* existing archive before deciding whether to fetch. A
    corrupted earlier capture blocks further collection instead of hiding it.
    A failed upstream request may be safely retried on the same date.
    """
    stamp = at if at is not None else datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ResearchCatalogError("daily collection requires timezone-aware UTC time")
    stamp = stamp.astimezone(timezone.utc)
    if start > end:
        raise ResearchCatalogError("daily collection date range is reversed")
    if root.is_symlink():
        raise ResearchCatalogError("archive root symlink refused")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir() or root.stat().st_mode & 0o077:
        raise ResearchCatalogError("daily archive root must be private (0700)")
    # A separate hidden file is ignored by QQQ capture inventory discovery.
    lock_file = root / ".nasdaq-qqq-daily.lock"
    if lock_file.is_symlink():
        raise ResearchCatalogError("archive collection lock symlink refused")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ResearchCatalogError("OS does not support no-follow daily lock")
    try:
        import fcntl
    except ImportError as exc:
        raise ResearchCatalogError("OS does not support advisory daily capture lock") from exc

    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise ResearchCatalogError("daily collection lock must be private regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        before = audit_nasdaq_qqq_archive(root, start, end)
        latest = before.last_captured_at
        last_day = datetime.fromisoformat(latest).date() if latest is not None else None
        if last_day is not None and last_day > stamp.date():
            raise ResearchCatalogError("archive contains a later UTC collection date")
        if last_day == stamp.date():
            return {
                "status": "ALREADY_COLLECTED_TODAY",
                "collection_utc_date": stamp.date().isoformat(),
                "receipt": None,
                "inventory": before.record(),
                "point_in_time_verified": False,
                "broker_executable": False,
            }
        receipt = archive_nasdaq_qqq_snapshot(
            root,
            start,
            end,
            at=stamp,
            fetch_bytes=fetch_bytes,
        )
        after = audit_nasdaq_qqq_archive(root, start, end)
        if (
            after.capture_count != before.capture_count + 1
            or after.last_captured_at != stamp.isoformat()
        ):
            raise ResearchCatalogError("daily post-capture inventory mismatch")
        return {
            "status": "NEW_CAPTURE_VERIFIED",
            "collection_utc_date": stamp.date().isoformat(),
            "receipt": receipt.record(),
            "inventory": after.record(),
            "point_in_time_verified": False,
            "broker_executable": False,
        }
    finally:
        os.close(fd)
