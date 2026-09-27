from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore, digest
from runtime.persistent_queue import PersistentJobQueue
from runtime.queue import Job, JobStatus
from runtime.runtime_contracts import (
    EvaluationAttemptSnapshot,
    EvaluationJobSnapshot,
    EvaluationRetrySummary,
    EvaluationRuntimeSnapshot,
    EvidenceRuntimeSnapshot,
    KnowledgeRuntimeSnapshot,
    LatestEvaluationJobSnapshot,
    LLMRuntimeSnapshot,
    ManagedSystemSnapshot,
    RecoveryRuntimeSnapshot,
    ResearchIntentSnapshot,
    ResearchRuntimeSnapshot,
    RuntimeComponentSnapshot,
    RuntimeErrorSummary,
    RuntimeSnapshot,
    StrategyStateRuntimeSnapshot,
    WorkerRuntimeSnapshot,
)

_EVENT_PHASES: dict[str, str] = {
    "run_started": "STARTING",
    "generation_started": "GENERATION",
    "proposal_started": "PROPOSING",
    "proposal_completed": "PROPOSING",
    "proposal_failed": "PROPOSING",
    "preflight_completed": "VALIDATING",
    "repair_started": "REPAIRING",
    "repair_completed": "REPAIRING",
    "repair_failed": "REPAIRING",
    "repair_unavailable": "REPAIRING",
    "repair_skipped_duplicate": "REPAIRING",
    "evaluation_started": "BACKTESTING",
    "evaluation_completed": "BACKTESTING",
    "evaluation_failed": "BACKTESTING",
    "fallback_evaluation_started": "BACKTESTING",
    "fallback_evaluation_failed": "BACKTESTING",
    "generation_completed": "FINALIZING",
    "run_failed": "FAILED",
    "run_completed": "COMPLETED",
    "run_interrupted": "INTERRUPTED",
}
_PHASE_STALE_SECONDS: dict[str, float] = {
    "STARTING": 300.0,
    "GENERATION": 300.0,
    "PROPOSING": 600.0,
    "VALIDATING": 300.0,
    "REPAIRING": 600.0,
    "BACKTESTING": 1800.0,
    "FINALIZING": 300.0,
}
_TERMINAL_RESEARCH_STATUSES = {
    "COMPLETED",
    "COMPLETED_WITH_ERRORS",
    "COMPLETED_WITH_FALLBACKS",
    "FAILED",
    "INTERRUPTED",
}



def build_runtime_snapshot(
    state_dir: Path,
    *,
    managed_run_id: str | None,
    system_state: Mapping[str, object] | None = None,
    recovery_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a sanitized, typed operational snapshot without mutating runtime state."""

    return cast(
        dict[str, object],
        read_runtime_snapshot(
            state_dir,
            managed_run_id=managed_run_id,
            system_state=system_state,
            recovery_state=recovery_state,
        ).model_dump(mode="json"),
    )


def read_runtime_snapshot(
    state_dir: Path,
    *,
    managed_run_id: str | None,
    system_state: Mapping[str, object] | None = None,
    recovery_state: Mapping[str, object] | None = None,
) -> RuntimeSnapshot:
    research_payload = _read_json(state_dir / "system" / "autoresearch.json")
    research = _research_snapshot(research_payload)
    recent_attempts = _recent_attempt_records(
        state_dir,
        managed_run_id=managed_run_id,
    )
    jobs = _jobs_snapshot(
        state_dir,
        managed_run_id=managed_run_id,
        recent_attempts=recent_attempts,
    )
    evidence_events, evidence_integrity_error = _all_evidence_events(state_dir)
    evidence = _evidence_snapshot(
        research_run_id=research.research_run_id,
        events=evidence_events,
        integrity_error=evidence_integrity_error,
    )
    latest_job = _latest_job_record(recent_attempts)
    workers = _worker_snapshots(state_dir)
    llm = _llm_snapshot(state_dir)
    recovery = _recovery_snapshot(state_dir, recovery_state=recovery_state)
    knowledge = _knowledge_snapshot(
        state_dir,
        evidence_events=evidence_events,
        evidence_integrity_error=evidence_integrity_error,
    )
    strategy_state = _strategy_state_snapshot(
        state_dir,
        evidence_events=evidence_events,
        evidence_integrity_error=evidence_integrity_error,
    )
    system = _system_snapshot(
        managed_run_id=managed_run_id,
        system_state=system_state,
    )
    errors = _recent_errors(
        research=research,
        evaluation=jobs,
        latest_job=latest_job,
        workers=workers,
        llm=llm,
    )

    return RuntimeSnapshot(
        system=system,
        research=research,
        evaluation=jobs.model_copy(update={"latest_job": latest_job}),
        evidence=evidence,
        workers=workers,
        llm=llm,
        recovery=recovery,
        knowledge=knowledge,
        strategy_state=strategy_state,
        recent_errors=errors,
        orders_enabled=False,
    )


def _system_snapshot(
    *,
    managed_run_id: str | None,
    system_state: Mapping[str, object] | None,
) -> ManagedSystemSnapshot:
    if system_state is None:
        return ManagedSystemSnapshot(managed_run_id=managed_run_id)
    raw_components = system_state.get("components")
    components: list[RuntimeComponentSnapshot] = []
    if isinstance(raw_components, list):
        for raw in raw_components:
            if not isinstance(raw, Mapping):
                continue
            component_id = _text(raw.get("id"))
            if component_id is None:
                continue
            components.append(
                RuntimeComponentSnapshot(
                    id=component_id,
                    status=_text(raw.get("status")) or "UNKNOWN",
                    alive=raw.get("alive") if isinstance(raw.get("alive"), bool) else None,
                    pid=_int_or_none(raw.get("pid")),
                    active_jobs=_nonnegative_int(raw.get("active_jobs")),
                    queued_jobs=_nonnegative_int(raw.get("queued_jobs")),
                    mode=_text(raw.get("mode")),
                )
            )
    return ManagedSystemSnapshot(
        status=_text(system_state.get("status")) or "UNKNOWN",
        managed_run_id=managed_run_id or _text(system_state.get("managed_run_id")),
        started_at=_text(system_state.get("started_at")),
        evaluation_execution=_text(system_state.get("evaluation_execution")),
        components=components,
    )


def _research_snapshot(payload: Mapping[str, object] | None) -> ResearchRuntimeSnapshot:
    if payload is None:
        return ResearchRuntimeSnapshot()

    status = _text(payload.get("status")) or "UNKNOWN"
    current_generation = _int_or_none(payload.get("current_generation"))
    current_phase = _text(payload.get("current_phase")) or "UNKNOWN"
    completed = _nonnegative_int(payload.get("completed_generations"))
    requested = _nonnegative_int(payload.get("requested_generations"))
    phase_started_at = _text(payload.get("phase_started_at"))
    last_event = _text(payload.get("last_event"))
    last_event_at = _text(payload.get("last_event_at"))
    now = datetime.now(timezone.utc)
    phase_age = _age_seconds(phase_started_at, now=now)
    event_age = _age_seconds(last_event_at, now=now)
    stale_after = _PHASE_STALE_SECONDS.get(current_phase)
    is_stale = (
        status == "RUNNING"
        and stale_after is not None
        and event_age is not None
        and event_age > stale_after
    )
    records = _generation_records(payload)
    last_completed = records[-1] if records else None
    non_degraded = [
        record for record in records if _text(record.get("status")) != "DEGRADED"
    ]
    last_non_degraded = non_degraded[-1] if non_degraded else None
    issues = _research_consistency_issues(
        status=status,
        current_generation=current_generation,
        current_phase=current_phase,
        completed=completed,
        requested=requested,
        last_event=last_event,
        records=records,
    )
    consistency_status: Literal["OK", "WARN", "UNKNOWN"] = (
        "UNKNOWN"
        if status in {"NOT_STARTED", "UNKNOWN"} and not records
        else "WARN"
        if issues
        else "OK"
    )
    return ResearchRuntimeSnapshot(
        status=status,
        research_run_id=_text(payload.get("research_run_id")),
        current_generation=current_generation,
        current_phase=current_phase,
        completed_generations=completed,
        requested_generations=requested,
        completion_percent=_completion_percent(completed, requested),
        last_completed_generation=(
            _int_or_none(last_completed.get("generation"))
            if last_completed is not None
            else None
        ),
        last_completed_status=(
            _text(last_completed.get("status")) if last_completed is not None else None
        ),
        last_non_degraded_generation=(
            _int_or_none(last_non_degraded.get("generation"))
            if last_non_degraded is not None
            else None
        ),
        phase_started_at=phase_started_at,
        phase_age_seconds=phase_age,
        last_event=last_event,
        last_event_at=last_event_at,
        last_event_age_seconds=event_age,
        stale_after_seconds=stale_after,
        is_stale=is_stale,
        consistency_status=consistency_status,
        consistency_issues=issues,
        repair_attempt=_int_or_none(payload.get("repair_attempt")),
        repair_attempts_allowed=_int_or_none(payload.get("repair_attempts_allowed")),
        error_class=_error_class(payload.get("error")),
        timing_summary=_safe_timing_summary(payload.get("timing_summary")),
        current_intent=_current_intent_snapshot(payload),
    )


def _generation_records(
    payload: Mapping[str, object],
) -> list[Mapping[str, object]]:
    raw = payload.get("generations")
    if not isinstance(raw, list):
        return []
    records = [
        item
        for item in raw
        if isinstance(item, Mapping)
        and _int_or_none(item.get("generation")) is not None
    ]
    return sorted(
        records,
        key=lambda item: _int_or_none(item.get("generation")) or 0,
    )


def _completion_percent(completed: int, requested: int) -> float:
    if requested <= 0:
        return 0.0
    return round(min(100.0, max(0.0, completed * 100.0 / requested)), 1)


def _age_seconds(value: str | None, *, now: datetime) -> float | None:
    parsed = _datetime(value)
    if parsed is None:
        return None
    return round(max(0.0, (now - parsed).total_seconds()), 3)


def _research_consistency_issues(
    *,
    status: str,
    current_generation: int | None,
    current_phase: str,
    completed: int,
    requested: int,
    last_event: str | None,
    records: list[Mapping[str, object]],
) -> list[str]:
    issues: list[str] = []
    if requested > 0 and completed > requested:
        issues.append("COMPLETED_EXCEEDS_REQUESTED")
    if len(records) != completed:
        issues.append("GENERATION_RECORD_COUNT_MISMATCH")
    if current_generation is not None:
        if current_generation < completed:
            issues.append("CURRENT_GENERATION_BEHIND_COMPLETED")
        if requested > 0 and current_generation > requested:
            issues.append("CURRENT_GENERATION_EXCEEDS_REQUESTED")
    expected_phase = _EVENT_PHASES.get(last_event or "")
    if expected_phase is not None and expected_phase != current_phase:
        issues.append("EVENT_PHASE_MISMATCH")
    if status.startswith("COMPLETED"):
        if current_phase != "COMPLETED":
            issues.append("TERMINAL_PHASE_MISMATCH")
        if requested > 0 and completed != requested:
            issues.append("COMPLETED_RUN_GENERATION_MISMATCH")
    elif status == "FAILED" and current_phase != "FAILED":
        issues.append("TERMINAL_PHASE_MISMATCH")
    elif status == "INTERRUPTED" and current_phase != "INTERRUPTED":
        issues.append("TERMINAL_PHASE_MISMATCH")
    if status in _TERMINAL_RESEARCH_STATUSES and last_event is None:
        issues.append("TERMINAL_EVENT_MISSING")
    return issues


def _current_intent_snapshot(payload: Mapping[str, object]) -> ResearchIntentSnapshot:
    current_generation = _int_or_none(payload.get("current_generation"))
    generations = payload.get("generations")
    if current_generation is None or not isinstance(generations, list):
        return ResearchIntentSnapshot()
    record = next(
        (
            item
            for item in reversed(generations)
            if isinstance(item, Mapping)
            and _int_or_none(item.get("generation")) == current_generation
        ),
        None,
    )
    if not isinstance(record, Mapping):
        return ResearchIntentSnapshot()
    intent = record.get("intent")
    if not isinstance(intent, Mapping):
        return ResearchIntentSnapshot()
    raw_parents = intent.get("parent_ids")
    parents = (
        [item for item in raw_parents if isinstance(item, str) and item]
        if isinstance(raw_parents, (list, tuple))
        else []
    )
    operations = record.get("operations")
    operation_count = (
        len(operations)
        if isinstance(operations, list)
        else len(intent.get("operations", ()))
        if isinstance(intent.get("operations"), (list, tuple))
        else 0
    )
    return ResearchIntentSnapshot(
        status="AVAILABLE",
        generation=current_generation,
        intent_status=_text(record.get("intent_status")),
        mode=_text(intent.get("mode")),
        parent_ids=parents,
        operation_count=operation_count,
        repair_attempts=_nonnegative_int(record.get("repair_attempts")),
    )


def _jobs_snapshot(
    state_dir: Path,
    *,
    managed_run_id: str | None,
    recent_attempts: list[EvaluationAttemptSnapshot],
) -> EvaluationRuntimeSnapshot:
    queue = PersistentJobQueue(state_dir)
    jobs, read_status = queue.snapshot_jobs_with_status(managed_run_id=managed_run_id)
    if read_status == "UNAVAILABLE":
        return EvaluationRuntimeSnapshot(
            status="UNAVAILABLE",
            queue_health="UNAVAILABLE",
            queue_issues=["QUEUE_UNREADABLE"],
            recent_attempts=recent_attempts,
        )

    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.status.value] = counts.get(job.status.value, 0) + 1

    now = datetime.now(timezone.utc)
    terminal_statuses = {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.TIMED_OUT,
        JobStatus.CANCELLED,
        JobStatus.RETRY_EXHAUSTED,
    }
    terminal = [job for job in jobs if job.status in terminal_statuses]
    issues = _queue_health_issues(jobs, now=now)
    retry_summary = EvaluationRetrySummary(
        jobs_with_retries=sum(job.attempt >= 2 for job in jobs),
        retries_used=sum(max(0, job.attempt - 1) for job in jobs),
        retry_pending_jobs=sum(
            job.status is JobStatus.QUEUED and job.attempt > 0 for job in jobs
        ),
        retry_exhausted_jobs=counts.get(JobStatus.RETRY_EXHAUSTED.value, 0),
    )
    return EvaluationRuntimeSnapshot(
        status="READY",
        queue_health="WARN" if issues else "HEALTHY",
        queue_issues=issues,
        counts=counts,
        total_jobs=len(jobs),
        terminal_jobs=len(terminal),
        retry_summary=retry_summary,
        active_jobs=[
            _job_summary(job, now=now)
            for job in jobs
            if job.status is JobStatus.RUNNING
        ],
        queued_jobs=[
            _job_summary(job, now=now)
            for job in jobs
            if job.status is JobStatus.QUEUED
        ],
        recent_terminal_jobs=[
            _job_summary(job, now=now) for job in reversed(terminal[-20:])
        ],
        recent_attempts=recent_attempts,
    )


def _queue_health_issues(jobs: tuple[Job, ...], *, now: datetime) -> list[str]:
    issues: list[str] = []
    if any(
        job.status is JobStatus.RUNNING
        and job.lease_until is not None
        and job.lease_until <= now
        for job in jobs
    ):
        issues.append("EXPIRED_RUNNING_LEASE")
    if any(
        job.status is JobStatus.RUNNING and job.lease_until is None
        for job in jobs
    ):
        issues.append("RUNNING_LEASE_MISSING")
    if any(
        job.attempt < 0 or job.attempt > job.max_attempts
        for job in jobs
    ):
        issues.append("ATTEMPT_RANGE_INVALID")
    if any(
        job.status is JobStatus.QUEUED
        and job.attempt > 0
        and job.attempt >= job.max_attempts
        for job in jobs
    ):
        issues.append("QUEUED_WITHOUT_ATTEMPTS_REMAINING")
    if any(job.status is JobStatus.RETRY_EXHAUSTED for job in jobs):
        issues.append("RETRY_EXHAUSTED_PRESENT")
    if any(job.status in {JobStatus.FAILED, JobStatus.TIMED_OUT} for job in jobs):
        issues.append("TERMINAL_FAILURE_PRESENT")
    return issues


def _job_summary(job: Job, *, now: datetime) -> EvaluationJobSnapshot:
    lease_expired = (
        job.status is JobStatus.RUNNING
        and job.lease_until is not None
        and job.lease_until <= now
    )
    return EvaluationJobSnapshot(
        job_id=job.job_id,
        status=job.status.value,
        queue_attempt=job.attempt,
        max_attempts=job.max_attempts,
        retries_used=max(0, job.attempt - 1),
        attempts_remaining=max(0, job.max_attempts - job.attempt),
        retry_pending=job.status is JobStatus.QUEUED and job.attempt > 0,
        error_class=job.error_class,
        lease_until=job.lease_until.isoformat() if job.lease_until is not None else None,
        lease_expired=lease_expired,
    )


def _recent_attempt_records(
    state_dir: Path,
    *,
    managed_run_id: str | None,
) -> list[EvaluationAttemptSnapshot]:
    path = state_dir / "system" / "evaluation-jobs.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    attempts: list[EvaluationAttemptSnapshot] = []
    for raw in reversed(lines[-1024:]):
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
        attempts.append(
            EvaluationAttemptSnapshot(
                job_id=_text(payload.get("job_id")),
                status=_text(payload.get("status")),
                queue_attempt=_int_or_none(payload.get("queue_attempt")),
                max_attempts=_int_or_none(payload.get("max_attempts")),
                error_class=_text(payload.get("error_class")),
                execution_mode=_text(payload.get("execution_mode")),
                isolated=payload.get("isolated") is True,
                timeout_enforced=payload.get("timeout_enforced") is True,
                research_run_id=_text(payload.get("research_run_id")),
                attempt_id=_text(payload.get("attempt_id")),
                generation=_int_or_none(payload.get("generation")),
            )
        )
        if len(attempts) >= 20:
            break
    return attempts


def _latest_job_record(
    attempts: list[EvaluationAttemptSnapshot],
) -> LatestEvaluationJobSnapshot | None:
    if not attempts:
        return None
    attempt = attempts[0]
    return LatestEvaluationJobSnapshot(
        job_id=attempt.job_id,
        status=attempt.status,
        queue_attempt=attempt.queue_attempt,
        max_attempts=attempt.max_attempts,
        error_class=attempt.error_class,
        execution_mode=attempt.execution_mode,
        isolated=attempt.isolated,
        timeout_enforced=attempt.timeout_enforced,
        research_run_id=attempt.research_run_id,
        attempt_id=attempt.attempt_id,
        generation=attempt.generation,
    )


def _all_evidence_events(
    state_dir: Path,
) -> tuple[list[dict[str, Any]], bool]:
    store = EvidenceStore(state_dir)
    if not store.path.is_file():
        return [], False
    try:
        return store.events(), False
    except EvidenceIntegrityError:
        return [], True


def _evidence_snapshot(
    *,
    research_run_id: str | None,
    events: list[dict[str, Any]],
    integrity_error: bool,
) -> EvidenceRuntimeSnapshot:
    if integrity_error:
        return EvidenceRuntimeSnapshot(
            status="INTEGRITY_ERROR",
            link_status="INTEGRITY_ERROR",
            integrity_status="INTEGRITY_ERROR",
            research_run_id=research_run_id,
        )
    if research_run_id is None:
        return EvidenceRuntimeSnapshot(
            status="NOT_LINKED",
            link_status="NOT_LINKED",
            integrity_status="VERIFIED" if events else "NOT_PRESENT",
        )

    related = [
        event
        for event in events
        if event["payload"].get("research_run_id") == research_run_id
    ]
    if not related:
        return EvidenceRuntimeSnapshot(
            status="OPEN",
            link_status="MISSING_RUN",
            integrity_status="VERIFIED" if events else "NOT_PRESENT",
            research_run_id=research_run_id,
        )

    attempts = [event for event in related if event["kind"] == "attempt"]
    generations = [event for event in related if event["kind"] == "generation"]
    end = next((event for event in reversed(related) if event["kind"] == "end"), None)
    manifest = next((event for event in related if event["kind"] == "manifest"), None)
    last_attempt = attempts[-1] if attempts else None
    last_generation = generations[-1] if generations else None
    evidence_status = (
        (_text(end["payload"].get("status")) or "UNKNOWN")
        if end is not None
        else "OPEN"
    )
    return EvidenceRuntimeSnapshot(
        status=evidence_status,
        link_status="LINKED",
        integrity_status="VERIFIED",
        research_run_id=research_run_id,
        event_count=len(related),
        manifest_present=manifest is not None,
        attempt_count=len(attempts),
        generation_count=len(generations),
        last_event_id=_text(related[-1].get("id")),
        last_event_kind=_text(related[-1].get("kind")),
        last_attempt_id=(
            _text(last_attempt["payload"].get("attempt_id"))
            if last_attempt is not None
            else None
        ),
        last_attempt_status=(
            _text(last_attempt["payload"].get("status"))
            if last_attempt is not None
            else None
        ),
        last_generation=(
            _int_or_none(last_generation["payload"].get("generation"))
            if last_generation is not None
            else None
        ),
        last_generation_status=(
            _text(last_generation["payload"].get("status"))
            if last_generation is not None
            else None
        ),
        terminal_status=(
            _text(end["payload"].get("status")) if end is not None else None
        ),
        closed=end is not None,
    )


def _worker_snapshots(state_dir: Path) -> list[WorkerRuntimeSnapshot]:
    directory = state_dir / "worker-heartbeats"
    if not directory.is_dir():
        return []
    now = datetime.now(timezone.utc)
    workers: list[WorkerRuntimeSnapshot] = []
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        if payload is None:
            continue
        last = _datetime(_text(payload.get("last_heartbeat")))
        terminal = (_text(payload.get("status")) or "").upper() in {
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "RETRY_EXHAUSTED",
        }
        online_state: Literal['ONLINE', 'STALE', 'OFFLINE', 'UNKNOWN']
        if last is None:
            online_state = "UNKNOWN"
        else:
            age = max(0.0, (now - last).total_seconds())
            if terminal:
                online_state = "OFFLINE"
            elif age <= 60:
                online_state = "ONLINE"
            elif age <= 300:
                online_state = "STALE"
            else:
                online_state = "OFFLINE"
        workers.append(
            WorkerRuntimeSnapshot(
                worker_id=_text(payload.get("worker_id")) or path.stem,
                job_id=_text(payload.get("job_id")),
                role=_text(payload.get("role")) or "unknown",
                status=_text(payload.get("status")) or "UNKNOWN",
                last_heartbeat=_text(payload.get("last_heartbeat")),
                online_state=online_state,
                attempt=_nonnegative_int(payload.get("attempt")),
                error_class=_error_class(payload.get("error")),
            )
        )
    return workers


def _llm_snapshot(state_dir: Path) -> LLMRuntimeSnapshot:
    payload = _read_json(state_dir / "llm" / "status.json")
    if payload is None:
        return LLMRuntimeSnapshot()
    return LLMRuntimeSnapshot(
        provider=_text(payload.get("provider")) or "codex_desktop",
        status=_text(payload.get("status")) or "UNKNOWN",
        last_result=_text(payload.get("last_result")) or "UNKNOWN",
        last_call_at=_text(payload.get("last_call_at")),
        operation=_text(payload.get("operation")),
    )


def _recovery_snapshot(
    state_dir: Path,
    *,
    recovery_state: Mapping[str, object] | None,
) -> RecoveryRuntimeSnapshot:
    event = _latest_jsonl_record(state_dir / "system" / "recovery-events.jsonl")
    event_name = _text(event.get("event")) if event is not None else None
    current = recovery_state or {}
    interrupted = _text(current.get("interrupted_research_run_id"))
    status: Literal['NONE', 'RECOVERED', 'INTERRUPTED'] = (
        "INTERRUPTED"
        if interrupted is not None or event_name == "INTERRUPTED"
        else "RECOVERED"
        if event_name is not None
        else "NONE"
    )
    raw_evidence_closed = current.get("evidence_closed")
    evidence_closed = (
        raw_evidence_closed if isinstance(raw_evidence_closed, bool) else None
    )
    return RecoveryRuntimeSnapshot(
        status=status,
        last_event=event_name,
        last_event_at=_text(event.get("timestamp")) if event is not None else None,
        reconciled_jobs=_string_list(current.get("reconciled_jobs")),
        cancelled_orphaned_jobs=_string_list(current.get("cancelled_orphaned_jobs")),
        interrupted_research_run_id=interrupted,
        evidence_closed=evidence_closed,
    )


def _knowledge_snapshot(
    state_dir: Path,
    *,
    evidence_events: list[dict[str, Any]],
    evidence_integrity_error: bool,
) -> KnowledgeRuntimeSnapshot:
    path = state_dir / "knowledge.json"
    if evidence_integrity_error:
        return KnowledgeRuntimeSnapshot(
            status="MISSING" if not path.is_file() else "INVALID",
            sync_status="EVIDENCE_INTEGRITY_ERROR",
        )

    expected_ids = _expected_knowledge_experiment_ids(evidence_events)
    if not path.is_file():
        return KnowledgeRuntimeSnapshot(
            status="MISSING",
            sync_status="MISSING" if expected_ids else "NOT_APPLICABLE",
            evidence_experiment_count=len(expected_ids),
            missing_experiment_count=len(expected_ids),
            projection_coverage_percent=0.0 if expected_ids else 100.0,
        )

    payload = _read_json(path)
    if payload is None:
        return KnowledgeRuntimeSnapshot(
            status="INVALID",
            sync_status="INVALID",
            evidence_experiment_count=len(expected_ids),
            missing_experiment_count=len(expected_ids),
            projection_coverage_percent=0.0 if expected_ids else 100.0,
        )

    names = ("known_good", "known_bad", "unexplored", "interactions")
    if any(not isinstance(payload.get(name, []), list) for name in names):
        return KnowledgeRuntimeSnapshot(
            status="INVALID",
            sync_status="INVALID",
            evidence_experiment_count=len(expected_ids),
            missing_experiment_count=len(expected_ids),
            projection_coverage_percent=0.0 if expected_ids else 100.0,
        )

    knowledge_lists = {
        name: cast(list[object], payload.get(name, []))
        for name in names
    }
    projected_ids: set[str] = set()
    unverified_entries = 0
    for name in ("known_good", "known_bad", "unexplored"):
        for item in knowledge_lists[name]:
            if not isinstance(item, Mapping):
                unverified_entries += 1
                continue
            experiment_id = _text(item.get("experiment_id"))
            if experiment_id is None:
                unverified_entries += 1
            else:
                projected_ids.add(experiment_id)

    missing_ids = expected_ids - projected_ids
    sync_status: Literal["NOT_APPLICABLE", "IN_SYNC", "STALE"] = (
        "NOT_APPLICABLE"
        if not expected_ids
        else "IN_SYNC"
        if not missing_ids
        else "STALE"
    )
    coverage = (
        100.0
        if not expected_ids
        else round((len(expected_ids) - len(missing_ids)) * 100.0 / len(expected_ids), 1)
    )
    return KnowledgeRuntimeSnapshot(
        status="CONNECTED",
        sync_status=sync_status,
        known_good_count=len(knowledge_lists["known_good"]),
        known_bad_count=len(knowledge_lists["known_bad"]),
        unexplored_count=len(knowledge_lists["unexplored"]),
        interactions_count=len(knowledge_lists["interactions"]),
        evidence_experiment_count=len(expected_ids),
        projected_experiment_count=len(projected_ids),
        missing_experiment_count=len(missing_ids),
        unverified_entry_count=unverified_entries,
        projection_coverage_percent=coverage,
    )


def _expected_knowledge_experiment_ids(
    events: list[dict[str, Any]],
) -> set[str]:
    expected: set[str] = set()
    projected_statuses = {"REJECT", "NEAR_MISS", "SURVIVOR", "FRONTIER"}
    for event in events:
        if event.get("kind") != "attempt":
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        research_run_id = _text(payload.get("research_run_id"))
        attempt_id = _text(payload.get("attempt_id"))
        candidates = payload.get("candidates")
        if (
            research_run_id is None
            or attempt_id is None
            or not isinstance(candidates, list)
        ):
            continue
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                continue
            candidate_hash = _text(candidate.get("candidate_hash"))
            status = _text(candidate.get("status"))
            if candidate_hash is None or status not in projected_statuses:
                continue
            expected.add(
                digest([research_run_id, attempt_id, index, candidate_hash])
            )
    return expected


def _strategy_state_snapshot(
    state_dir: Path,
    *,
    evidence_events: list[dict[str, Any]],
    evidence_integrity_error: bool,
) -> StrategyStateRuntimeSnapshot:
    payload = _read_json(state_dir / "champion.json")
    if payload is None:
        return StrategyStateRuntimeSnapshot()

    nested = payload.get("champion")
    champion = nested if isinstance(nested, Mapping) else payload
    champion_hash = _text(champion.get("champion_hash"))
    audit_records, last_promotion_at, audit_invalid = _promotion_audit_summary(
        state_dir / "audit.jsonl"
    )
    if champion_hash is None:
        return StrategyStateRuntimeSnapshot(
            champion_status=_text(payload.get("status")) or "UNKNOWN",
            promotion_audit_status="NOT_APPLICABLE",
            frontier_status="NOT_CONNECTED",
            rescue_status="NOT_CONNECTED",
        )

    evidence_match = (
        None
        if evidence_integrity_error
        else _find_candidate_evidence(evidence_events, champion_hash)
    )
    evidence_status: Literal[
        "LINKED", "NOT_FOUND", "EVIDENCE_INTEGRITY_ERROR"
    ]
    if evidence_integrity_error:
        evidence_status = "EVIDENCE_INTEGRITY_ERROR"
    elif evidence_match is None:
        evidence_status = "NOT_FOUND"
    else:
        evidence_status = "LINKED"

    audit_status: Literal["PRESENT", "MISSING", "INVALID"]
    if audit_records > 0:
        audit_status = "PRESENT"
    elif audit_invalid:
        audit_status = "INVALID"
    else:
        audit_status = "MISSING"

    linked_payload: Mapping[str, object] | None = None
    linked_candidate: Mapping[str, object] | None = None
    if evidence_match is not None:
        linked_payload, linked_candidate = evidence_match
    linked_generation = (
        _int_or_none(linked_payload.get("generation"))
        if linked_payload is not None
        else None
    )
    return StrategyStateRuntimeSnapshot(
        champion_status=_text(champion.get("status"))
        or _text(payload.get("status"))
        or "UNKNOWN",
        champion_hash=champion_hash,
        champion_family=_text(champion.get("family")),
        champion_generation=_int_or_none(champion.get("generation")) or linked_generation,
        champion_score=_float_or_none(champion.get("score")),
        champion_evidence_status=evidence_status,
        champion_research_run_id=(
            _text(linked_payload.get("research_run_id"))
            if linked_payload is not None
            else None
        ),
        champion_attempt_id=(
            _text(linked_payload.get("attempt_id"))
            if linked_payload is not None
            else None
        ),
        champion_candidate_status=(
            _text(linked_candidate.get("status"))
            if linked_candidate is not None
            else None
        ),
        promotion_audit_status=audit_status,
        promotion_audit_records=audit_records,
        last_promotion_at=last_promotion_at,
        frontier_status="NOT_CONNECTED",
        rescue_status="NOT_CONNECTED",
    )


def _find_candidate_evidence(
    events: list[dict[str, Any]],
    candidate_hash: str,
) -> tuple[Mapping[str, object], Mapping[str, object]] | None:
    for event in reversed(events):
        if event.get("kind") != "attempt":
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if (
                isinstance(candidate, Mapping)
                and candidate.get("candidate_hash") == candidate_hash
            ):
                return payload, candidate
    return None


def _promotion_audit_summary(path: Path) -> tuple[int, str | None, bool]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0, None, False
    count = 0
    last_at: str | None = None
    invalid = False
    for raw in lines:
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            invalid = True
            continue
        if not isinstance(payload, dict):
            invalid = True
            continue
        if payload.get("event") != "promote_champion":
            continue
        count += 1
        timestamp = _text(payload.get("timestamp"))
        if timestamp is not None:
            last_at = timestamp
    return count, last_at, invalid


def _recent_errors(
    *,
    research: ResearchRuntimeSnapshot,
    evaluation: EvaluationRuntimeSnapshot,
    latest_job: LatestEvaluationJobSnapshot | None,
    workers: list[WorkerRuntimeSnapshot],
    llm: LLMRuntimeSnapshot,
) -> list[RuntimeErrorSummary]:
    candidates: list[tuple[str, str | None]] = [
        ("research", research.error_class),
        ("evaluation_latest", latest_job.error_class if latest_job is not None else None),
        *[
            (f"worker:{worker.worker_id}", worker.error_class)
            for worker in workers
        ],
    ]
    for job in (*evaluation.active_jobs, *evaluation.queued_jobs):
        candidates.append((f"job:{job.job_id}", job.error_class))
    if llm.status.upper() in {"OFFLINE", "FAILED", "ERROR"}:
        candidates.append(("llm", _safe_error_token(llm.last_result)))
    seen: set[tuple[str, str]] = set()
    result: list[RuntimeErrorSummary] = []
    for source, error_class in candidates:
        if error_class is None:
            continue
        key = (source, error_class)
        if key in seen:
            continue
        seen.add(key)
        result.append(RuntimeErrorSummary(source=source, error_class=error_class))
        if len(result) >= 8:
            break
    return result


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
            if metric
            in {
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


def _latest_jsonl_record(path: Path) -> dict[str, Any] | None:
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
        if isinstance(payload, dict):
            return payload
    return None


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


def _safe_error_token(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    token = text.split(":", 1)[0].strip()
    return token if token and token.replace("_", "").isalnum() else "ProviderError"


def _datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (
        parsed.astimezone(timezone.utc)
        if parsed.tzinfo is not None
        else parsed.replace(tzinfo=timezone.utc)
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _nonnegative_int(value: object) -> int:
    result = _int_or_none(value)
    return result if result is not None and result >= 0 else 0
