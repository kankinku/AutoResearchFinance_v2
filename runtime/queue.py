from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


@dataclass
class Job:
    job_id: str
    payload: dict[str, Any]
    status: JobStatus = JobStatus.QUEUED
    attempt: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def enqueue(self, job: Job) -> None:
        if job.job_id in self._jobs:
            raise ValueError(f"job already exists: {job.job_id}")
        self._jobs[job.job_id] = job

    def claim(self) -> Job | None:
        for job in self._jobs.values():
            if job.status is JobStatus.QUEUED:
                job.status = JobStatus.RUNNING
                job.attempt += 1
                return job
        return None

    def succeed(self, job_id: str, result: dict[str, Any]) -> None:
        job = self.get(job_id)
        self._require_running(job)
        job.result = result
        job.status = JobStatus.SUCCEEDED

    def fail(self, job_id: str, error: str) -> None:
        job = self.get(job_id)
        self._require_running(job)
        job.error = error
        job.status = JobStatus.FAILED

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
