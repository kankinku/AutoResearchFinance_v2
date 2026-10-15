"""Offline audited inventory of locally captured Nasdaq QQQ price vintages.

The local archive proves only retained-byte integrity and revisions observed
between retrievals. It does not prove publisher-side historical release times,
PIT tradability, OOS validation or permission to place brokerage orders.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from core.integrity.hashes import content_hash
from research.indicator_engine.capture_integrity import verify_nasdaq_capture
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.verified_capture_vintages import (
    CapturedPriceVintage,
    compare_verified_nasdaq_vintages,
)

MAX_CAPTURES = 512
MAX_EXAMPLES = 32
_NEW_DIR = re.compile(
    r"qqq_(\d{4}-\d\d-\d\d)_(\d{4}-\d\d-\d\d)_(\d{8}T\d{12}Z)"
)
_STATUS = Literal[
    "NO_CAPTURES",
    "INSUFFICIENT_COLLECTION_DAYS",
    "COLLECTION_DATE_GAPS",
    "OBSERVED_REVISIONS",
    "OBSERVED_COLLECTION_SEQUENCE_STABLE",
]


@dataclass(frozen=True)
class NasdaqArchiveInventory:
    status: _STATUS
    capture_count: int
    verified_capture_count: int
    distinct_collection_days: int
    first_captured_at: str | None
    last_captured_at: str | None
    compared_consecutive_pairs: int
    total_compared_bars: int
    total_revised_bars: int
    revised_date_examples: tuple[str, ...]
    missing_collection_days: int
    missing_collection_dates: tuple[str, ...]
    inventory_hash: str
    point_in_time_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "capture_count": self.capture_count,
            "verified_capture_count": self.verified_capture_count,
            "distinct_collection_days": self.distinct_collection_days,
            "first_captured_at": self.first_captured_at,
            "last_captured_at": self.last_captured_at,
            "compared_consecutive_pairs": self.compared_consecutive_pairs,
            "total_compared_bars": self.total_compared_bars,
            "total_revised_bars": self.total_revised_bars,
            "revised_date_examples": list(self.revised_date_examples),
            "missing_collection_days": self.missing_collection_days,
            "missing_collection_dates": list(self.missing_collection_dates),
            "collection_cadence": "one UTC calendar date; illustrative, not exchange sessions",
            "inventory_hash": self.inventory_hash,
            "independence": "SAME_PROVIDER_LOCAL_CAPTURE_TIMES",
            "independent_historical_publication_verified": False,
            "captured_raw_bytes_exported": False,
            "point_in_time_verified": False,
            "broker_executable": False,
        }


def _reject_nonprivate(path: Path, *, directory: bool) -> None:
    if path.is_symlink():
        raise ResearchCatalogError("archive symlink refused")
    if not path.exists() or (not path.is_dir() if directory else not path.is_file()):
        raise ResearchCatalogError("archive capture file or directory missing")
    if path.stat().st_mode & 0o077:
        raise ResearchCatalogError("archive must use private permissions")


def _capture_triplet(folder: Path, prefix: str) -> CapturedPriceVintage:
    files = (
        folder / (prefix + ".parquet"),
        folder / (prefix + ".raw.json"),
        folder / (prefix + ".manifest.json"),
    )
    for path in files:
        _reject_nonprivate(path, directory=False)
    return CapturedPriceVintage(*files)


def _discover(root: Path) -> list[tuple[CapturedPriceVintage, str | None]]:
    records: list[tuple[CapturedPriceVintage, str | None]] = []
    legacy: set[str] = set()
    for item in root.iterdir():
        name = item.name
        if not name.startswith("qqq_"):
            continue
        if item.is_symlink():
            raise ResearchCatalogError("archive symlink refused")
        if item.is_dir():
            matched = _NEW_DIR.fullmatch(name)
            if matched is None:
                raise ResearchCatalogError("invalid archive QQQ capture directory")
            _reject_nonprivate(item, directory=True)
            records.append((_capture_triplet(item, "qqq"), matched.group(3)))
        else:
            if not name.startswith("qqq_archive_"):
                raise ResearchCatalogError("unexpected QQQ archival source file")
            for suffix in (".parquet", ".raw.json", ".manifest.json"):
                if name.endswith(suffix):
                    legacy.add(name[:-len(suffix)])
                    break
            else:
                raise ResearchCatalogError("unknown legacy capture format")
    for prefix in sorted(legacy):
        records.append((_capture_triplet(root, prefix), None))
    if len(records) > MAX_CAPTURES:
        raise ResearchCatalogError("archive capture limit exceeded")
    return records


def audit_nasdaq_qqq_archive(
    root: Path,
    start: date,
    end: date,
) -> NasdaqArchiveInventory:
    """Verify every matching archived source and consecutive price revision pair.

    Collection date cadence is UTC-calendar based. Same-day captures don't
    establish a multi-day record, and local clocks/manifest hashes aren't
    historical publication timestamp attestation.
    """
    if start > end:
        raise ValueError("archive date range reversed")
    if root.is_symlink():
        raise ResearchCatalogError("archive root symlink refused")
    if root.exists():
        _reject_nonprivate(root, directory=True)
        captures = _discover(root)
    else:
        captures = []
    ordered: list[tuple[datetime, CapturedPriceVintage, str]] = []
    now = datetime.now(timezone.utc)
    for triple, directory_stamp in captures:
        verified = verify_nasdaq_capture(
            triple.parquet_path, triple.raw_path, triple.manifest_path
        )
        try:
            manifest = json.loads(triple.manifest_path.read_text(encoding="utf-8"))
            stamp = datetime.fromisoformat(manifest["captured_at"])
            source = urlsplit(manifest["source_url"])
            fields = parse_qs(source.query, strict_parsing=True)
            scope = (date.fromisoformat(fields["fromdate"][0]),
                     date.fromisoformat(fields["todate"][0]))
        except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
            raise ResearchCatalogError("archive timestamp or scope invalid") from exc
        if scope != (start, end):
            raise ResearchCatalogError("archive capture scope differs")
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ResearchCatalogError("archive collection timestamp timezone missing")
        when = stamp.astimezone(timezone.utc)
        if when > now + timedelta(minutes=5):
            raise ResearchCatalogError("archive capture timestamp lies in the future")
        if (
            directory_stamp is not None
            and when.strftime("%Y%m%dT%H%M%S%fZ") != directory_stamp
        ):
            raise ResearchCatalogError("archive timestamp does not match folder label")
        ordered.append((when, triple, verified.capture_hash))
    ordered.sort(key=lambda item: item[0])
    stamps = [item[0] for item in ordered]
    if len(set(stamps)) != len(stamps):
        raise ResearchCatalogError("duplicate archive capture timestamps")
    day_set = {at.date() for at in stamps}
    missing = []
    if day_set:
        first, last = min(day_set), max(day_set)
        for n in range((last - first).days + 1):
            d = first + timedelta(days=n)
            if d not in day_set:
                missing.append(d.isoformat())
    total_revised = 0
    total_compared = 0
    modified_dates: set[str] = set()
    pair_hashes = []
    for old, new in zip(ordered, ordered[1:], strict=False):
        comparison = compare_verified_nasdaq_vintages(old[1], new[1])
        total_revised += comparison.changed_bars
        total_compared += comparison.comparable_bars
        modified_dates.update(comparison.changed_session_dates)
        pair_hashes.append(comparison.pair_hash)
    status: _STATUS
    if not captures:
        status = "NO_CAPTURES"
    elif len(day_set) < 2:
        status = "INSUFFICIENT_COLLECTION_DAYS"
    elif missing:
        status = "COLLECTION_DATE_GAPS"
    elif total_revised:
        status = "OBSERVED_REVISIONS"
    else:
        status = "OBSERVED_COLLECTION_SEQUENCE_STABLE"
    chain = content_hash({
        "schema": "qqq-archive-inventory-v1",
        "scope_start": start.isoformat(),
        "scope_end": end.isoformat(),
        "captures": [
            {"collected_at": stamp.isoformat(), "capture_hash": digest}
            for stamp, _triple, digest in ordered
        ],
        "comparison_hashes": pair_hashes,
    })
    return NasdaqArchiveInventory(
        status=status,
        capture_count=len(ordered),
        verified_capture_count=len(ordered),
        distinct_collection_days=len(day_set),
        first_captured_at=stamps[0].isoformat() if stamps else None,
        last_captured_at=stamps[-1].isoformat() if stamps else None,
        compared_consecutive_pairs=len(pair_hashes),
        total_compared_bars=total_compared,
        total_revised_bars=total_revised,
        revised_date_examples=tuple(sorted(modified_dates)[:MAX_EXAMPLES]),
        missing_collection_days=len(missing),
        missing_collection_dates=tuple(missing[:MAX_EXAMPLES]),
        inventory_hash=chain,
    )
