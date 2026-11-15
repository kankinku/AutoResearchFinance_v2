"""Transactional, immutable evidence events. Readers never create state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


class EvidenceIntegrityError(ValueError):
    """Evidence cannot safely be recorded or interpreted."""


def encode(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(payload: object) -> str:
    return hashlib.sha256(encode(payload).encode("utf-8")).hexdigest()


def _validate(kind: str, payload: dict[str, Any]) -> None:
    required = {
        "run": ("requested_generations", "seed"),
        "manifest": ("comparison_key",),
        "attempt": ("attempt_id", "generation", "status", "candidates"),
        "generation": ("generation", "status", "attempt_id"),
        "end": ("status",),
    }
    if kind not in required or any(k not in payload for k in required[kind]):
        raise EvidenceIntegrityError("invalid event shape")
    if not isinstance(payload.get("research_run_id"), str) or not payload["research_run_id"]:
        raise EvidenceIntegrityError("invalid run identity")
    for field in ("generation", "requested_generations"):
        if field in payload and (type(payload[field]) is not int or payload[field] < 1):
            raise EvidenceIntegrityError("invalid generation count")
    if kind == "manifest" and not isinstance(payload["comparison_key"], str):
        raise EvidenceIntegrityError("invalid comparison identity")
    if kind in {"attempt", "generation", "end"} and not isinstance(payload["status"], str):
        raise EvidenceIntegrityError("invalid event status")
    if kind == "attempt":
        if not isinstance(payload["attempt_id"], str) or not isinstance(
            payload["candidates"], list
        ):
            raise EvidenceIntegrityError("invalid attempt shape")
        for candidate in payload["candidates"]:
            if (
                not isinstance(candidate, dict)
                or any(
                    not isinstance(candidate.get(field), str)
                    for field in ("candidate_hash", "status", "family")
                )
                or not isinstance(candidate.get("failed_gates"), list)
            ):
                raise EvidenceIntegrityError("invalid candidate shape")
            if any(not isinstance(g, str) for g in candidate["failed_gates"]):
                raise EvidenceIntegrityError("invalid gate name")


class EvidenceStore:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "system" / "research-evidence" / "evidence.sqlite"

    def append(self, kind: str, event_id: str, payload: dict[str, Any]) -> None:
        if kind not in {"run", "manifest", "attempt", "generation", "end"}:
            raise EvidenceIntegrityError("invalid event kind")
        if not event_id or not isinstance(payload.get("research_run_id"), str):
            raise EvidenceIntegrityError("event identity required")
        serialized = encode(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(self.path, timeout=30) as connection:
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS events ("
                    "seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, "
                    "payload TEXT NOT NULL, checksum TEXT NOT NULL)"
                )
                for action in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"CREATE TRIGGER IF NOT EXISTS prevent_{action.lower()} "
                        f"BEFORE {action} ON events BEGIN "
                        "SELECT RAISE(ABORT, 'immutable evidence'); END"
                    )
                # Composite expression index supports both a fast per-run
                # lookup and a global malformed-run-ID check. Index creation
                # on legacy files fails closed if stored JSON is invalid.
                # No event row or immutable trigger is migrated or replaced.
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_run_identity ON events "
                    "(json_type(payload, '$.research_run_id'), "
                    "json_extract(payload, '$.research_run_id'), kind)"
                )
                connection.execute("BEGIN IMMEDIATE")
                prior = connection.execute(
                    "SELECT kind, payload, checksum FROM events WHERE id=?", (event_id,)
                ).fetchone()
                expected = (kind, serialized, digest([event_id, kind, payload]))
                if prior is not None:
                    if prior != expected:
                        raise EvidenceIntegrityError("event identity conflict")
                    return
                _validate(kind, payload)
                # Never ignore corrupt legacy identities, including rows in
                # another run. This uses the index rather than decoding every
                # historical payload in Python on every append.
                if connection.execute(
                    "SELECT 1 FROM events WHERE "
                    "json_type(payload, '$.research_run_id') IS NOT 'text' "
                    "LIMIT 1"
                ).fetchone() is not None:
                    raise EvidenceIntegrityError("invalid stored run identity")
                related_kinds = [
                    existing_kind
                    for (existing_kind,) in connection.execute(
                        "SELECT kind FROM events WHERE "
                        "json_type(payload, '$.research_run_id')='text' "
                        "AND json_extract(payload, '$.research_run_id')=? "
                        "AND kind IN ('run', 'manifest', 'end')",
                        (payload["research_run_id"],),
                    )
                ]
                if "end" in related_kinds:
                    raise EvidenceIntegrityError("research run is closed")
                if kind != "run" and "run" not in related_kinds:
                    raise EvidenceIntegrityError("research run must be registered")
                if kind in {"run", "manifest"} and kind in related_kinds:
                    raise EvidenceIntegrityError("event identity conflict")
                connection.execute(
                    "INSERT INTO events(id, kind, payload, checksum) VALUES (?, ?, ?, ?)",
                    (event_id, *expected),
                )
        except sqlite3.Error as exc:
            raise EvidenceIntegrityError("evidence write failed") from exc

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
                rows = conn.execute("SELECT id, kind, payload, checksum FROM events ORDER BY seq")
                result = []
                for event_id, kind, serialized, checksum in rows:
                    payload = json.loads(serialized)
                    if (
                        not isinstance(payload, dict)
                        or digest([event_id, kind, payload]) != checksum
                    ):
                        raise EvidenceIntegrityError("evidence checksum mismatch")
                    _validate(kind, payload)
                    result.append({"id": event_id, "kind": kind, "payload": payload})
                return result
        except (sqlite3.Error, json.JSONDecodeError, TypeError) as exc:
            raise EvidenceIntegrityError("evidence read failed") from exc
