"""Conservative append-only archive of real public Nasdaq QQQ latest-revision quotes.

Captures raw response bytes + parsed daily DEVELOPMENT Parquet + manifest.
Local timestamps are NOT independent authenticated historical release times.
No execution, sealed OOS access, or point-in-time promotion is possible.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from research.indicator_engine.capture_integrity import verify_nasdaq_capture
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_capture import _http_fetch, capture_nasdaq_qqq


@dataclass(frozen=True)
class NasdaqArchiveReceipt:
    directory: Path
    parquet_path: Path
    raw_path: Path
    manifest_path: Path
    captured_at: str
    raw_sha256: str
    capture_hash: str
    verified_rows: int
    integrity_status: Literal["LOCAL_CAPTURE_BYTES_VERIFIED"] = (
        "LOCAL_CAPTURE_BYTES_VERIFIED"
    )
    point_in_time_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "directory": str(self.directory),
            "parquet_path": str(self.parquet_path),
            "raw_path": str(self.raw_path),
            "manifest_path": str(self.manifest_path),
            "captured_at": self.captured_at,
            "raw_sha256": self.raw_sha256,
            "capture_hash": self.capture_hash,
            "verified_rows": self.verified_rows,
            "integrity_status": self.integrity_status,
            "point_in_time_verified": False,
            "broker_executable": False,
            "independent_historical_publication_verified": False,
        }


def archive_nasdaq_qqq_snapshot(
    root: Path, start: date, end: date, *,
    at: datetime | None = None,
    fetch_bytes: Callable[[str], bytes] = _http_fetch,
) -> NasdaqArchiveReceipt:
    """Write one new unique private capture directory, never overwrite existing bytes.

    The machine-supplied timestamp is when collection started, not when the
    historical publisher first made any price data available. Follow-up captures
    must happen at genuine later wall-clock times.
    """
    captured = at if at is not None else datetime.now(timezone.utc)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ResearchCatalogError("capture timestamp timezone is required")
    utc = captured.astimezone(timezone.utc)
    key = utc.strftime("%Y%m%dT%H%M%S%fZ")
    root = root.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    archive = root / f"qqq_{start.isoformat()}_{end.isoformat()}_{key}"
    try:
        archive.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as exc:
        raise ResearchCatalogError("immutable capture archive already exists") from exc
    output = archive / "qqq.parquet"
    raw = archive / "qqq.raw.json"
    manifest = archive / "qqq.manifest.json"
    try:
        original = capture_nasdaq_qqq(
            start, end, output, raw, manifest,
            captured_at=utc, fetch_bytes=fetch_bytes,
        )
        verified = verify_nasdaq_capture(output, raw, manifest)
        if (
            verified.raw_sha256 != original.raw_sha256
            or verified.dataset_hash != original.dataset_hash
            or verified.verified_rows != original.row_count
        ):
            raise ResearchCatalogError("captured source replay does not match original")
        for path in (output, raw, manifest):
            path.chmod(0o600)
        archive.chmod(0o700)
    except Exception:
        # Remove only this freshly reserved, previously nonexistent directory;
        # never remove earlier archives on a failed new capture.
        for path in (output, raw, manifest):
            path.unlink(missing_ok=True)
        archive.rmdir()
        raise
    return NasdaqArchiveReceipt(
        directory=archive,
        parquet_path=output,
        raw_path=raw,
        manifest_path=manifest,
        captured_at=original.captured_at,
        raw_sha256=verified.raw_sha256,
        capture_hash=verified.capture_hash,
        verified_rows=verified.verified_rows,
    )
