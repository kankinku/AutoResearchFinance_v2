from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore


def mark_autoresearch_interrupted(state_dir: Path) -> dict[str, object] | None:
    """Convert a stale RUNNING projection into an explicit interrupted state."""

    path = state_dir / "system" / "autoresearch.json"
    payload = _read_json(path)
    if payload is None or payload.get("status") != "RUNNING":
        return None
    now = datetime.now(timezone.utc).isoformat()
    payload["status"] = "INTERRUPTED"
    payload["current_phase"] = "INTERRUPTED"
    payload["last_event"] = "run_interrupted"
    payload["last_event_at"] = now
    payload["phase_started_at"] = now
    payload["phase_elapsed_seconds"] = 0.0
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return interruption_origin(payload)


def close_interrupted_evidence(
    state_dir: Path,
    *,
    research_run_id: str | None,
) -> bool:
    if research_run_id is None:
        return False
    store = EvidenceStore(state_dir)
    try:
        events = [
            event
            for event in store.events()
            if event["payload"].get("research_run_id") == research_run_id
        ]
        if any(event["kind"] == "end" for event in events):
            return False
        store.append(
            "end",
            f"end:{research_run_id}",
            {
                "research_run_id": research_run_id,
                "status": "INTERRUPTED",
            },
        )
    except EvidenceIntegrityError:
        return False
    return True


def append_recovery_event(
    state_dir: Path,
    *,
    event: str,
    managed_run_id: str | None,
    origin: dict[str, object] | None = None,
    replacement_managed_run_id: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "managed_run_id": managed_run_id,
        "orders_enabled": False,
    }
    if origin is not None:
        payload["origin"] = origin
    if replacement_managed_run_id is not None:
        payload["replacement_managed_run_id"] = replacement_managed_run_id
    target = state_dir / "system" / "recovery-events.jsonl"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return


def interruption_origin(payload: dict[str, Any]) -> dict[str, object]:
    return {
        "research_run_id": _text(payload.get("research_run_id")),
        "completed_generations": _nonnegative_int(payload.get("completed_generations")),
        "requested_generations": _nonnegative_int(payload.get("requested_generations")),
        "current_generation": _int_or_none(payload.get("current_generation")),
        "current_phase": _text(payload.get("current_phase")),
        "last_event": _text(payload.get("last_event")),
        "last_event_at": _text(payload.get("last_event_at")),
    }


def runtime_interruption_origin(runtime: object) -> dict[str, object] | None:
    if not isinstance(runtime, dict):
        return None
    research = runtime.get("research")
    if not isinstance(research, dict) or research.get("status") != "INTERRUPTED":
        return None
    return {
        "research_run_id": _text(research.get("research_run_id")),
        "completed_generations": _nonnegative_int(research.get("completed_generations")),
        "requested_generations": _nonnegative_int(research.get("requested_generations")),
        "current_generation": _int_or_none(research.get("current_generation")),
        "current_phase": _text(research.get("current_phase")),
        "last_event": _text(research.get("last_event")),
        "last_event_at": _text(research.get("last_event_at")),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _nonnegative_int(value: object) -> int:
    result = _int_or_none(value)
    return result if result is not None and result >= 0 else 0
