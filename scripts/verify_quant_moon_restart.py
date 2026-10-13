"""Read-only before/after identity verification for Moon Quant MCP restart.

Never restarts services, calls the broker, reads sealed OOS, or emits credentials.
External Windows Docker restart and Supervisor restart are separate procedures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from memory.evidence_store import digest as evidence_digest


class RestartVerificationError(ValueError):
    """No completed acceptance can be claimed while identity differs."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _required_bytes(path: Path, label: str) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RestartVerificationError(f"{label} persisted identity missing") from exc
    if not data:
        raise RestartVerificationError(f"{label} persisted identity is empty")
    return data


def _table_fingerprint(path: Path, table: str, label: str) -> tuple[str, int]:
    if not path.is_file():
        raise RestartVerificationError(f"{label} database missing")
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            columns = [str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")]
            if not columns:
                raise RestartVerificationError(f"{label} expected table missing")
            rows = db.execute(f"SELECT * FROM {table}").fetchall()
            normalized = sorted(
                json.dumps(
                    list(row),
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                    ensure_ascii=False,
                )
                for row in rows
            )
    except sqlite3.Error as exc:
        raise RestartVerificationError(f"{label} read-only verification failed") from exc
    return evidence_digest({"columns": columns, "rows": normalized}), len(rows)


def capture(moon_state: Path) -> dict[str, Any]:
    """Capture sensitive fingerprints; caller must store baseline with mode 0600."""
    state = moon_state.resolve()
    research = state / "research"
    fingerprints = {
        "approval_key": _sha(_required_bytes(state / "oauth" / "approval-key", "approval")),
        "public_url_pin": _sha(
            _required_bytes(state / "oauth" / "public-base-url", "public OAuth URL")
        ),
    }
    specs = {
        "oauth_clients": (research / "oauth" / "quant-oauth.sqlite", "clients"),
        "oauth_grants": (research / "oauth" / "quant-oauth.sqlite", "grants"),
        "batches": (research / "system" / "gpt-research-batches.sqlite", "batches"),
        "generation_history": (
            research / "system" / "gpt-research-batches.sqlite",
            "generation_history",
        ),
        "generation_checkpoints": (
            research / "system" / "gpt-research-batches.sqlite",
            "generation_checkpoints",
        ),
        "guided_sessions": (research / "system" / "gpt-guided-sessions.sqlite", "sessions"),
        "guided_steps": (research / "system" / "gpt-guided-sessions.sqlite", "steps"),
    }
    counts: dict[str, int] = {}
    for label, (db_path, table) in specs.items():
        value, count = _table_fingerprint(db_path, table, label)
        fingerprints[label] = value
        counts[label] = count
    # Check the ledger's own event checksums, not just SQLite page or mtime.
    try:
        events = EvidenceStore(research).events()
    except EvidenceIntegrityError as exc:
        raise RestartVerificationError("Evidence checksum or shape invalid") from exc
    if not (research / "system" / "research-evidence" / "evidence.sqlite").is_file():
        raise RestartVerificationError("Evidence database missing")
    fingerprints["research_evidence"] = evidence_digest(events)
    counts["evidence_events"] = len(events)
    with sqlite3.connect(
        (research / "system" / "gpt-research-batches.sqlite").resolve().as_uri() + "?mode=ro",
        uri=True,
    ) as db:
        active = db.execute(
            "SELECT COUNT(*) FROM batches WHERE status IN ('RUNNING','QUEUED')"
        ).fetchone()[0]
    if active:
        raise RestartVerificationError("active research batches: do not restart")
    return {
        "version": 1,
        "orders_enabled": False,
        "fingerprints": fingerprints,
        "counts": counts,
        "status": "BASELINE_CAPTURED",
    }


def verify(moon_state: Path, baseline: dict[str, Any]) -> dict[str, Any]:
    if (
        baseline.get("version") != 1
        or baseline.get("orders_enabled") is not False
        or not isinstance(baseline.get("fingerprints"), dict)
        or not isinstance(baseline.get("counts"), dict)
    ):
        raise RestartVerificationError("invalid restart baseline")
    current = capture(moon_state)
    for label, original in baseline["fingerprints"].items():
        if current["fingerprints"].get(label) != original:
            raise RestartVerificationError(f"{label} persisted identity changed")
    if current["counts"] != baseline["counts"]:
        raise RestartVerificationError("persistent research state counts changed")
    return {
        "status": "PASS",
        "orders_enabled": False,
        "oauth_clients": current["counts"]["oauth_clients"],
        "evidence_events": current["counts"]["evidence_events"],
        "research_batches": current["counts"]["batches"],
        "guided_sessions": current["counts"]["guided_sessions"],
        "checks": len(current["fingerprints"]),
    }


def _secure_snapshot(baseline: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(destination, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(baseline, handle, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Quant restart integrity audit")
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--moon-state", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.phase == "before":
            snapshot = capture(args.moon_state)
            _secure_snapshot(snapshot, args.baseline)
            response = {
                "status": "BASELINE_CAPTURED",
                "orders_enabled": False,
                "oauth_clients": snapshot["counts"]["oauth_clients"],
                "evidence_events": snapshot["counts"]["evidence_events"],
                "baseline_recorded": True,
            }
        else:
            saved = json.loads(args.baseline.read_text(encoding="utf-8"))
            response = verify(args.moon_state, saved)
        print(json.dumps(response, sort_keys=True))
        return 0
    except (RestartVerificationError, OSError, ValueError, TypeError) as exc:
        # Expose only stable diagnostic field labels, never sqlite rows or secrets.
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "orders_enabled": False,
                    "reason": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
