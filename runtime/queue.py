from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


@dataclass
class Job:
    job_id: str
    payload: dict[str, Any]
    status: JobStatus = JobStatus.QUEUED
    attempt: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    error_class: str | None = None
    lease_until: datetime | None = None
    max_attempts: int = 3


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def enqueue(self, job: Job) -> None:
        if job.job_id in self._jobs:
            raise ValueError(f"job already exists: {job.job_id}")
        self._jobs[job.job_id] = job

    def claim(self, *, lease_seconds: float = 300.0) -> Job | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        for job in self._jobs.values():
            if job.status is JobStatus.QUEUED:
                job.status = JobStatus.RUNNING
                job.attempt += 1
                job.lease_until = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
                return job
        return None

    def reconcile_stale(self, *, now: datetime | None = None) -> tuple[str, ...]:
        current = now or datetime.now(timezone.utc)
        reconciled: list[str] = []
        for job in self._jobs.values():
            if job.status is not JobStatus.RUNNING or job.lease_until is None:
                continue
            if job.lease_until > current:
                continue
            if job.attempt >= job.max_attempts:
                job.status = JobStatus.RETRY_EXHAUSTED
                job.error = "worker lease expired after maximum attempts"
            else:
                job.status = JobStatus.QUEUED
                job.error = "worker lease expired; queued for retry"
            job.lease_until = None
            reconciled.append(job.job_id)
        return tuple(reconciled)

    def succeed(self, job_id: str, result: dict[str, Any]) -> None:
        job = self.get(job_id)
        self._require_running(job)
        job.result = result
        job.error = None
        job.error_class = None
        job.status = JobStatus.SUCCEEDED
        job.lease_until = None

    def fail(self, job_id: str, error: str, *, error_class: str | None = None) -> None:
        job = self.get(job_id)
        self._require_running(job)
        job.error = error
        job.error_class = error_class
        job.status = JobStatus.FAILED
        job.lease_until = None

    def retry_failed(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status is not JobStatus.FAILED:
            raise ValueError(f"job is not failed: {job.job_id}")
        if job.attempt >= job.max_attempts:
            job.status = JobStatus.RETRY_EXHAUSTED
            job.error = "worker failed after maximum attempts"
            return
        job.status = JobStatus.QUEUED
        job.result = None
        job.lease_until = None

    def get(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"unknown job: {job_id}") from exc

    def pending(self) -> int:
        return sum(job.status is JobStatus.QUEUED for job in self._jobs.values())

    def _require_running(self, job: Job) -> None:
        if job.status is not JobStatus.RUNNING:
            raise ValueError(f"job is not running: {job.job_id}")
