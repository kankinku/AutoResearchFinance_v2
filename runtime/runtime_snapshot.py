from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from runtime.persistent_queue import PersistentJobQueue
from runtime.queue import Job, JobStatus


def build_runtime_snapshot(
    state_dir: Path,
    *,
    managed_run_id: str | None,
) -> dict[str, object]:
    """Build a sanitized operational snapshot from durable runtime state."""

    research = _research_snapshot(state_dir)
    research_run_id = _text(research.get("research_run_id"))
    jobs = _jobs_snapshot(state_dir, managed_run_id=managed_run_id)
    evidence = _evidence_snapshot(state_dir, research_run_id=research_run_id)
    latest_job = _latest_job_record(state_dir, managed_run_id=managed_run_id)

    return {
        "research": research,
        "evaluation": {
            **jobs,
            "latest_job": latest_job,
        },
        "evidence": evidence,
        "orders_enabled": False,
    }


def _research_snapshot(state_dir: Path) -> dict[str, object]:
    payload = _read_json(state_dir / "system" / "autoresearch.json")
    if payload is None:
        return {
            "status": "NOT_STARTED",
            "current_generation": None,
            "current_phase": "UNKNOWN",
            "completed_generations": 0,
            "requested_generations": 0,
            "research_run_id": None,
        }
    return {
        "status": _text(payload.get("status")) or "UNKNOWN",
        "research_run_id": _text(payload.get("research_run_id")),
        "current_generation": _int_or_none(payload.get("current_generation")),
        "current_phase": _text(payload.get("current_phase")) or "UNKNOWN",
        "completed_generations": _nonnegative_int(payload.get("completed_generations")),
        "requested_generations": _nonnegative_int(payload.get("requested_generations")),
        "last_event": _text(payload.get("last_event")),
        "last_event_at": _text(payload.get("last_event_at")),
        "repair_attempt": _int_or_none(payload.get("repair_attempt")),
        "repair_attempts_allowed": _int_or_none(
            payload.get("repair_attempts_allowed")
        ),
        "error_class": _error_class(payload.get("error")),
        "timing_summary": _safe_timing_summary(payload.get("timing_summary")),
    }


def _jobs_snapshot(
    state_dir: Path,
    *,
    managed_run_id: str | None,
) -> dict[str, object]:
    queue = PersistentJobQueue(state_dir)
    try:
        jobs = (
            queue.jobs_for_run(managed_run_id)
            if managed_run_id is not None
            else (*queue.running(), *queue.queued())
        )
    except (OSError, ValueError):
        return {
            "status": "UNAVAILABLE",
            "counts": {},
            "active_jobs": [],
            "queued_jobs": [],
        }

    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.status.value] = counts.get(job.status.value, 0) + 1
    return {
        "status": "READY",
        "counts": counts,
        "active_jobs": [_job_summary(job) for job in jobs if job.status is JobStatus.RUNNING],
        "queued_jobs": [_job_summary(job) for job in jobs if job.status is JobStatus.QUEUED],
    }


def _job_summary(job: Job) -> dict[str, object]:
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "queue_attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "error_class": job.error_class,
        "lease_until": job.lease_until.isoformat() if job.lease_until is not None else None,
    }


def _latest_job_record(
    state_dir: Path,
    *,
    managed_run_id: str | None,
) -> dict[str, object] | None:
    path = state_dir / "system" / "evaluation-jobs.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for raw in reversed(lines[-512:]):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if managed_run_id is not None and payload.get("managed_run_id") != managed_run_id:
            continue
        return {
            "job_id": _text(payload.get("job_id")),
            "status": _text(payload.get("status")),
            "queue_attempt": _int_or_none(payload.get("queue_attempt")),
            "max_attempts": _int_or_none(payload.get("max_attempts")),
            "error_class": _text(payload.get("error_class")),
            "execution_mode": _text(payload.get("execution_mode")),
            "isolated": payload.get("isolated") is True,
            "timeout_enforced": payload.get("timeout_enforced") is True,
            "research_run_id": _text(payload.get("research_run_id")),
            "attempt_id": _text(payload.get("attempt_id")),
            "generation": _int_or_none(payload.get("generation")),
        }
    return None


def _evidence_snapshot(
    state_dir: Path,
    *,
    research_run_id: str | None,
) -> dict[str, object]:
    if research_run_id is None:
        return {
            "status": "NOT_LINKED",
            "research_run_id": None,
            "event_count": 0,
            "closed": False,
        }
    try:
        events = [
            event
            for event in EvidenceStore(state_dir).events()
            if event["payload"].get("research_run_id") == research_run_id
        ]
    except EvidenceIntegrityError:
        return {
            "status": "INTEGRITY_ERROR",
            "research_run_id": research_run_id,
            "event_count": 0,
            "closed": False,
        }
    end = next((event for event in reversed(events) if event["kind"] == "end"), None)
    return {
        "status": (
            _text(end["payload"].get("status"))
            if end is not None
            else "OPEN"
        ),
        "research_run_id": research_run_id,
        "event_count": len(events),
        "last_event_kind": events[-1]["kind"] if events else None,
        "closed": end is not None,
    }


def _safe_timing_summary(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not isinstance(raw, dict):
            continue
        result[key] = {
            metric: metric_value
            for metric, metric_value in raw.items()
            if metric in {
                "count",
                "total_seconds",
                "p50_seconds",
                "p95_seconds",
                "max_seconds",
            }
            and isinstance(metric_value, (int, float))
            and not isinstance(metric_value, bool)
        }
    return result


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _error_class(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    head = value.split(":", 1)[0].strip()
    return head if head and head.replace("_", "").isalnum() else "RuntimeError"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _nonnegative_int(value: object) -> int:
    result = _int_or_none(value)
    return result if result is not None and result >= 0 else 0
