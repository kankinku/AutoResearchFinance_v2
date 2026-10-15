"""Offline, research-only Databento dataset-condition vintage archive and comparison.

This inspects local *dataset-level metadata*, not Nasdaq ITCH market packets.
It never connects to a paid endpoint. Local capture times and SHA-256 pins are
not independently authenticated historic as-of/publication-time witnesses.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nyse_public_calendar import _closed_dates

_DATASET = "XNAS.ITCH"
_SCHEMA = "databento-dataset-condition-vintage-v1"
_ENVIRONMENTS = frozenset(("production", "preview"))
_MAX_BYTES = 512_000
_MAX_DATES = 2500
_MAX_EXAMPLES = 25
_META_KEYS = frozenset((
    "schema", "dataset", "environment", "coverage_start", "coverage_end",
    "captured_at", "raw_sha256", "condition_rows",
))


@dataclass(frozen=True)
class ConditionVintage:
    path: Path
    captured_at: datetime
    environment: str
    coverage_start: date
    coverage_end: date
    rows: dict[date, tuple[str, str | None]]
    raw_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class DatabentoConditionChange:
    status: Literal["CONDITION_REVISIONS_OBSERVED", "CONDITION_METADATA_UNCHANGED"]
    compared_days: int
    changed_days: int
    changed_dates: tuple[str, ...]
    earlier_captured_at: str
    later_captured_at: str
    environment_pair: str
    earlier_raw_sha256: str
    later_raw_sha256: str
    pair_hash: str
    source_bytes_reverified: Literal[True] = True
    post_cutover_production_verified: Literal[False] = False
    market_packet_revisions_verified: Literal[False] = False
    historical_pit_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "compared_days": self.compared_days,
            "changed_days": self.changed_days,
            "changed_dates": list(self.changed_dates),
            "earlier_captured_at": self.earlier_captured_at,
            "later_captured_at": self.later_captured_at,
            "environment_pair": self.environment_pair,
            "earlier_raw_sha256": self.earlier_raw_sha256,
            "later_raw_sha256": self.later_raw_sha256,
            "pair_hash": self.pair_hash,
            "source_bytes_reverified": True,
            "post_cutover_production_verified": False,
            "market_packet_revisions_verified": False,
            "historical_pit_verified": False,
            "broker_executable": False,
            "independent_timestamp_attestation_verified": False,
            "data_scope": "dataset_level_not_symbol_or_schema_specific",
        }


def _read_rows(data: bytes, start: date, end: date) -> dict[date, tuple[str, str | None]]:
    if not 0 < len(data) <= _MAX_BYTES:
        raise ResearchCatalogError("condition response bytes missing or oversized")
    if start > end or start < date(2020, 1, 1) or end > date(2026, 12, 31):
        raise ResearchCatalogError("condition audit outside pinned date scope")
    try:
        payload = json.loads(data)
        if not isinstance(payload, list) or not payload or len(payload) > _MAX_DATES:
            raise ValueError("condition rows invalid")
        rows: dict[date, tuple[str, str | None]] = {}
        for item in payload:
            if not isinstance(item, dict) or set(item) != {
                "date", "condition", "last_modified_date"
            }:
                raise ValueError("condition object invalid")
            session = date.fromisoformat(item["date"])
            condition = item["condition"]
            modified = item["last_modified_date"]
            if (
                session < start or session > end or session in rows
                or condition not in ("available", "degraded", "pending", "missing")
                or (condition == "missing" and modified is not None)
                or (condition != "missing" and not isinstance(modified, str))
            ):
                raise ValueError("condition duplicate, scope or quality invalid")
            if modified is not None:
                modification = date.fromisoformat(modified)
                if modification < session or modification > datetime.now(timezone.utc).date():
                    raise ValueError("condition modification timestamp outside possible period")
            rows[session] = (condition, modified)
        closed = _closed_dates()
        expected = {
            start + timedelta(days=i)
            for i in range((end-start).days+1)
            if (start+timedelta(days=i)).weekday() < 5
            and start+timedelta(days=i) not in closed
        }
        if any(rows.get(day, (None,))[0] != "available" for day in expected):
            raise ValueError("condition regular-session coverage incomplete or degraded")
        return rows
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise ResearchCatalogError("condition scope or response invalid") from exc


def _private(path: Path, *, directory: bool) -> None:
    if path.is_symlink() or not path.exists():
        raise ResearchCatalogError("condition evidence missing or symlinked")
    if (not path.is_dir() if directory else not path.is_file()):
        raise ResearchCatalogError("condition evidence wrong file type")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ResearchCatalogError("condition evidence permissions are not private")


def preserve_condition_snapshot(
    root: Path, *, raw_conditions: bytes, environment: str,
    start: date, end: date, captured_at: datetime | None = None,
) -> Path:
    """Append a new local capture; only genuine provider bytes should enter production.

    The date is self-asserted system time, not an issuer/exchange timestamp.
    Caller-supplied bytes in tests are synthetic and never PIT proof.
    """
    if environment not in _ENVIRONMENTS:
        raise ResearchCatalogError("condition source environment invalid")
    when = captured_at or datetime.now(timezone.utc)
    if when.tzinfo is None or when.utcoffset() is None:
        raise ResearchCatalogError("condition collection timezone missing")
    when = when.astimezone(timezone.utc)
    if when > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ResearchCatalogError("condition collection timestamp is in the future")
    rows = _read_rows(raw_conditions, start, end)
    if any(
        modified is not None and date.fromisoformat(modified) > when.date()
        for _state, modified in rows.values()
    ):
        raise ResearchCatalogError("condition record modified after capture time")
    if root.is_symlink():
        raise ResearchCatalogError("condition archive root symlinked")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private(root, directory=True)
    name = (
        f"{_DATASET.replace('.', '-')}_{environment}_"
        f"{start.isoformat()}_{end.isoformat()}_{when.strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    folder = root / name
    try:
        folder.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as exc:
        raise ResearchCatalogError("condition capture already exists") from exc
    raw = folder / "conditions.json"
    manifest = folder / "manifest.json"
    try:
        meta = {
            "schema": _SCHEMA, "dataset": _DATASET,
            "environment": environment, "coverage_start": start.isoformat(),
            "coverage_end": end.isoformat(), "captured_at": when.isoformat(),
            "raw_sha256": hashlib.sha256(raw_conditions).hexdigest(),
            "condition_rows": len(rows),
        }
        with raw.open("xb") as file:
            file.write(raw_conditions)
        with manifest.open("xb") as file:
            file.write(json.dumps(meta, sort_keys=True, separators=(",", ":")).encode())
        raw.chmod(0o600)
        manifest.chmod(0o600)
        folder.chmod(0o700)
        _load(folder)
    except Exception:
        for path in (manifest, raw):
            path.unlink(missing_ok=True)
        folder.rmdir()
        raise
    return folder


def _load(folder: Path) -> ConditionVintage:
    _private(folder, directory=True)
    raw_path, manifest_path = folder / "conditions.json", folder / "manifest.json"
    _private(raw_path, directory=False)
    _private(manifest_path, directory=False)
    try:
        m_bytes = manifest_path.read_bytes()
        if not 0 < len(m_bytes) <= 4096:
            raise ValueError("manifest size")
        manifest = json.loads(m_bytes)
        if (
            not isinstance(manifest, dict) or frozenset(manifest) != _META_KEYS
            or manifest["schema"] != _SCHEMA or manifest["dataset"] != _DATASET
            or manifest["environment"] not in _ENVIRONMENTS
            or json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            != m_bytes
        ):
            raise ValueError("manifest identity mismatch")
        when = datetime.fromisoformat(manifest["captured_at"])
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError("timestamp tz")
        when = when.astimezone(timezone.utc)
        if when > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("future timestamp")
        start = date.fromisoformat(manifest["coverage_start"])
        end = date.fromisoformat(manifest["coverage_end"])
        rows_data = raw_path.read_bytes()
        digest = hashlib.sha256(rows_data).hexdigest()
        if digest != manifest["raw_sha256"]:
            raise ValueError("raw hash mismatch")
        rows = _read_rows(rows_data, start, end)
        if any(
            modified is not None and date.fromisoformat(modified) > when.date()
            for _state, modified in rows.values()
        ):
            raise ValueError("condition modified in the future of collection")
        if len(rows) != manifest["condition_rows"]:
            raise ValueError("rows count mismatch")
        if folder.name != (
            f"{_DATASET.replace('.', '-')}_{manifest['environment']}_"
            f"{start.isoformat()}_{end.isoformat()}_{when.strftime('%Y%m%dT%H%M%S%fZ')}"
        ):
            raise ValueError("directory timestamp/scope mismatch")
        return ConditionVintage(folder, when, manifest["environment"],
                                start, end, rows, digest,
                                hashlib.sha256(m_bytes).hexdigest())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ResearchCatalogError("condition archive failed replay integrity") from exc


def compare_condition_vintages(earlier: Path, later: Path) -> DatabentoConditionChange:
    """Compare independently stored local vendor metadata revisions, never price PIT."""
    a = _load(earlier)
    b = _load(later)
    if a.path.resolve() == b.path.resolve() or a.captured_at >= b.captured_at:
        raise ResearchCatalogError("condition vintage chronology invalid")
    if (a.coverage_start, a.coverage_end) != (b.coverage_start, b.coverage_end):
        raise ResearchCatalogError("condition vintage scope incomparable")
    if set(a.rows) != set(b.rows):
        raise ResearchCatalogError("condition vintage record-date sets incomparable")
    changed = tuple(sorted(day.isoformat() for day in a.rows if a.rows[day] != b.rows[day]))
    chain = content_hash({
        "schema": "databento-condition-comparison-v1",
        "a": (a.captured_at.isoformat(), a.manifest_sha256, a.raw_sha256),
        "b": (b.captured_at.isoformat(), b.manifest_sha256, b.raw_sha256),
        "environment_pair": (a.environment, b.environment),
        "changed_dates": changed,
    })
    return DatabentoConditionChange(
        status=("CONDITION_REVISIONS_OBSERVED" if changed
                else "CONDITION_METADATA_UNCHANGED"),
        compared_days=len(a.rows),
        changed_days=len(changed),
        changed_dates=changed[:_MAX_EXAMPLES],
        earlier_captured_at=a.captured_at.isoformat(),
        later_captured_at=b.captured_at.isoformat(),
        environment_pair=f"{a.environment}→{b.environment}",
        earlier_raw_sha256=a.raw_sha256,
        later_raw_sha256=b.raw_sha256,
        pair_hash=chain,
    )
