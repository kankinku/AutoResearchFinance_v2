from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from runtime.queue import Job, JobStatus


class PersistentJobQueue:
    """SQLite-backed queue shared safely across host and worker processes."""

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "system" / "evaluation-jobs" / "queue.sqlite"

    def enqueue(self, job: Job) -> None:
        if job.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._write(
            """
            INSERT INTO jobs(
                job_id, payload, status, attempt, result, error, error_class,
                lease_until, max_attempts, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                _encode(job.payload),
                job.status.value,
                job.attempt,
                _encode(job.result) if job.result is not None else None,
                job.error,
                job.error_class,
                _timestamp(job.lease_until),
                job.max_attempts,
                _timestamp(_now()),
            ),
            duplicate_message=f"job already exists: {job.job_id}",
        )

    def claim(
        self,
        *,
        job_id: str | None = None,
        lease_seconds: float = 300.0,
    ) -> Job | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self._ensure_schema()
        with sqlite3.connect(self.path, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if job_id is None:
                row = connection.execute(
                    """
                    SELECT job_id, payload, status, attempt, result, error, error_class,
                           lease_until, max_attempts
                    FROM jobs
                    WHERE status=?
                    ORDER BY updated_at, job_id
                    LIMIT 1
                    """,
                    (JobStatus.QUEUED.value,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT job_id, payload, status, attempt, result, error, error_class,
                           lease_until, max_attempts
                    FROM jobs
                    WHERE job_id=? AND status=?
                    """,
                    (job_id, JobStatus.QUEUED.value),
                ).fetchone()
            if row is None:
                connection.commit()
                return None
            current = _row_to_job(row)
            current.status = JobStatus.RUNNING
            current.attempt += 1
            current.lease_until = _now() + timedelta(seconds=lease_seconds)
            connection.execute(
                """
                UPDATE jobs
                SET status=?, attempt=?, lease_until=?, error=NULL, error_class=NULL,
                    updated_at=?
                WHERE job_id=? AND status=?
                """,
                (
                    current.status.value,
                    current.attempt,
                    _timestamp(current.lease_until),
                    _timestamp(_now()),
                    current.job_id,
                    JobStatus.QUEUED.value,
                ),
            )
            connection.commit()
            return current

    def get(self, job_id: str) -> Job:
        self._ensure_schema()
        with sqlite3.connect(self.path, timeout=30) as connection:
            row = connection.execute(
                """
                SELECT job_id, payload, status, attempt, result, error, error_class,
                       lease_until, max_attempts
                FROM jobs
                WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown job: {job_id}")
        return _row_to_job(row)

    def succeed(self, job_id: str, result: dict[str, Any]) -> None:
        self._transition_running(
            job_id,
            JobStatus.SUCCEEDED,
            result=result,
            error=None,
            error_class=None,
        )

    def fail(
        self,
        job_id: str,
        error: str,
        *,
        error_class: str | None = None,
    ) -> None:
        self._transition_running(
            job_id,
            JobStatus.FAILED,
            result=None,
            error=error,
            error_class=error_class,
        )

    def timeout(self, job_id: str, *, error_class: str = "TimeoutError") -> None:
        self._transition_running(
            job_id,
            JobStatus.TIMED_OUT,
            result=None,
            error="worker timed out",
            error_class=error_class,
        )

    def abort_running(
        self,
        job_id: str,
        *,
        error_class: str = "WorkerProcessError",
    ) -> None:
        self._transition_running(
            job_id,
            JobStatus.FAILED,
            result=None,
            error="worker process exited before completing the job",
            error_class=error_class,
        )

    def retry_terminal(self, job_id: str) -> None:
        self._ensure_schema()
        with sqlite3.connect(self.path, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, attempt, max_attempts FROM jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown job: {job_id}")
            status = JobStatus(row[0])
            attempt = int(row[1])
            max_attempts = int(row[2])
            if status not in {JobStatus.FAILED, JobStatus.TIMED_OUT}:
                raise ValueError(f"job is not retryable: {job_id}")
            next_status = (
                JobStatus.RETRY_EXHAUSTED
                if attempt >= max_attempts
                else JobStatus.QUEUED
            )
            connection.execute(
                """
                UPDATE jobs
                SET status=?, result=NULL, lease_until=NULL,
                    error=?, updated_at=?
                WHERE job_id=?
                """,
                (
                    next_status.value,
                    (
                        "worker failed after maximum attempts"
                        if next_status is JobStatus.RETRY_EXHAUSTED
                        else None
                    ),
                    _timestamp(_now()),
                    job_id,
                ),
            )
            connection.commit()

    def running(self) -> tuple[Job, ...]:
        self._ensure_schema()
        with sqlite3.connect(self.path, timeout=30) as connection:
            rows = connection.execute(
                """
                SELECT job_id, payload, status, attempt, result, error, error_class,
                       lease_until, max_attempts
                FROM jobs
                WHERE status=?
                ORDER BY updated_at, job_id
                """,
                (JobStatus.RUNNING.value,),
            ).fetchall()
        return tuple(_row_to_job(row) for row in rows)

    def cancel_running(self, job_id: str) -> None:
        self._transition_running(
            job_id,
            JobStatus.CANCELLED,
            result=None,
            error="system stopped while worker was running",
            error_class="SystemStopped",
        )

    def reconcile_stale(self, *, now: datetime | None = None) -> tuple[str, ...]:
        self._ensure_schema()
        current = now or _now()
        reconciled: list[str] = []
        with sqlite3.connect(self.path, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT job_id, attempt, max_attempts
                FROM jobs
                WHERE status=? AND lease_until IS NOT NULL AND lease_until<=?
                ORDER BY job_id
                """,
                (JobStatus.RUNNING.value, _timestamp(current)),
            ).fetchall()
            for job_id, attempt, max_attempts in rows:
                exhausted = int(attempt) >= int(max_attempts)
                connection.execute(
                    """
                    UPDATE jobs
                    SET status=?, lease_until=NULL, error=?, error_class=?,
                        updated_at=?
                    WHERE job_id=? AND status=?
                    """,
                    (
                        (
                            JobStatus.RETRY_EXHAUSTED.value
                            if exhausted
                            else JobStatus.QUEUED.value
                        ),
                        (
                            "worker lease expired after maximum attempts"
                            if exhausted
                            else "worker lease expired; queued for retry"
                        ),
                        "LeaseExpired",
                        _timestamp(current),
                        job_id,
                        JobStatus.RUNNING.value,
                    ),
                )
                reconciled.append(str(job_id))
            connection.commit()
        return tuple(reconciled)

    def _transition_running(
        self,
        job_id: str,
        status: JobStatus,
        *,
        result: dict[str, Any] | None,
        error: str | None,
        error_class: str | None,
    ) -> None:
        self._ensure_schema()
        with sqlite3.connect(self.path, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status=?, result=?, error=?, error_class=?, lease_until=NULL,
                    updated_at=?
                WHERE job_id=? AND status=?
                """,
                (
                    status.value,
                    _encode(result) if result is not None else None,
                    error,
                    error_class,
                    _timestamp(_now()),
                    job_id,
                    JobStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ValueError(f"job is not running: {job_id}")
            connection.commit()

    def _write(
        self,
        statement: str,
        values: tuple[object, ...],
        *,
        duplicate_message: str,
    ) -> None:
        self._ensure_schema()
        try:
            with sqlite3.connect(self.path, timeout=30) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(statement, values)
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(duplicate_message) from exc

    def _ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=30) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    result TEXT,
                    error TEXT,
                    error_class TEXT,
                    lease_until TEXT,
                    max_attempts INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )


def _row_to_job(row: tuple[object, ...]) -> Job:
    return Job(
        job_id=str(row[0]),
        payload=_decode_object(row[1]),
        status=JobStatus(str(row[2])),
        attempt=_db_int(row[3], "attempt"),
        result=_decode_optional_object(row[4]),
        error=str(row[5]) if row[5] is not None else None,
        error_class=str(row[6]) if row[6] is not None else None,
        lease_until=_datetime(row[7]),
        max_attempts=_db_int(row[8], "max_attempts"),
    )




def _db_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"queue {name} is invalid")
    return value

def _encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _decode_object(value: object) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ValueError("queue payload is invalid")
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("queue payload is invalid")
    return decoded


def _decode_optional_object(value: object) -> dict[str, Any] | None:
    return None if value is None else _decode_object(value)


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("queue timestamp is invalid")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("queue timestamp must be timezone-aware")
    return parsed


def _now() -> datetime:
    return datetime.now(timezone.utc)
