from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from research.policy import load_policy
from runtime.heartbeat import WorkerHeartbeatStore
from runtime.queue import Job, JobQueue, JobStatus
from runtime.resource_manager import ResourceManager
from runtime.scheduler import LocalScheduler

EvaluationCallable = Callable[..., dict[str, object]]

_RETRYABLE_ERRORS = {
    "BrokenPipeError",
    "ConnectionError",
    "TimeoutError",
}


class EvaluationExecutionError(RuntimeError):
    """Raised when the scheduled evaluation worker cannot complete a job."""


class QueuedEvaluationExecutor:
    """Run evaluations through the repository's queue/scheduler worker boundary.

    This is a local worker boundary, not Docker isolation. The execution record
    states that explicitly so downstream evidence never confuses the two modes.
    """

    def __init__(
        self,
        state_dir: Path,
        *,
        max_concurrency: int | None = None,
        max_retries: int | None = None,
        lease_seconds: float | None = None,
    ) -> None:
        policy = load_policy(
            Path(__file__).resolve().parents[1] / "research" / "policy.yaml"
        ).runtime
        self.state_dir = state_dir.resolve()
        self.max_concurrency = (
            policy.max_concurrency if max_concurrency is None else max_concurrency
        )
        self.max_retries = policy.max_retries if max_retries is None else max_retries
        self.lease_seconds = float(
            policy.job_timeout_seconds if lease_seconds is None else lease_seconds
        )
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.resources = ResourceManager(max_concurrency=self.max_concurrency)
        self._log_lock = threading.Lock()
        self.heartbeat_store = WorkerHeartbeatStore(
            self.state_dir / "worker-heartbeats"
        )

    def run(
        self,
        evaluator: EvaluationCallable,
        **kwargs: Any,
    ) -> dict[str, object]:
        queue = JobQueue()
        job_id = _job_id(kwargs.get("attempt_id"))
        job = Job(
            job_id,
            _job_payload(kwargs),
            max_attempts=self.max_retries + 1,
        )
        queue.enqueue(job)
        scheduler = LocalScheduler(
            queue,
            self.resources,
            heartbeat_store=self.heartbeat_store,
            lease_seconds=self.lease_seconds,
        )

        while True:
            def execute(current_job: Job) -> dict[str, object]:
                call_kwargs = dict(kwargs)
                call_kwargs["execution_context"] = {
                    "job_id": current_job.job_id,
                    "queue_attempt": current_job.attempt,
                    "max_attempts": current_job.max_attempts,
                    "execution_mode": "local_scheduler",
                    "isolated": False,
                    "timeout_enforced": False,
                    "lease_seconds": self.lease_seconds,
                }
                return evaluator(**call_kwargs)

            results = scheduler.run(execute)
            current = results[job_id]
            if current.status is JobStatus.SUCCEEDED:
                if current.result is None:
                    raise EvaluationExecutionError("evaluation worker returned no result")
                self._record_attempt(current, kwargs, current.result)
                return current.result
            if (
                current.status is JobStatus.FAILED
                and current.error_class in _RETRYABLE_ERRORS
                and current.attempt < current.max_attempts
            ):
                self._record_attempt(current, kwargs, None)
                queue.retry_failed(job_id)
                continue
            if (
                current.status is JobStatus.FAILED
                and current.error_class in _RETRYABLE_ERRORS
                and current.attempt >= current.max_attempts
            ):
                queue.retry_failed(job_id)
            self._record_attempt(current, kwargs, None)
            error = current.error or "evaluation worker failed"
            raise EvaluationExecutionError(error)

    def _record_attempt(
        self,
        job: Job,
        kwargs: dict[str, Any],
        result: dict[str, object] | None,
    ) -> None:
        research_run_id = _string_or_none(kwargs.get("research_run_id"))
        attempt_id = _string_or_none(kwargs.get("attempt_id"))
        if result is not None:
            research_run_id = research_run_id or _string_or_none(result.get("research_run_id"))
            attempt_id = attempt_id or _string_or_none(result.get("attempt_id"))
        payload = {
            "job_id": job.job_id,
            "research_run_id": research_run_id,
            "attempt_id": attempt_id,
            "generation": _int_or_none(kwargs.get("generation")),
            "status": job.status.value,
            "queue_attempt": job.attempt,
            "max_attempts": job.max_attempts,
            "error_class": job.error_class,
            "execution_mode": "local_scheduler",
            "isolated": False,
            "timeout_enforced": False,
            "lease_seconds": self.lease_seconds,
        }
        target = self.state_dir / "system" / "evaluation-jobs.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._log_lock:
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _job_id(attempt_id: object) -> str:
    if isinstance(attempt_id, str) and attempt_id:
        safe = "".join(
            char if char.isalnum() or char in "._-" else "-"
            for char in attempt_id
        )
        return f"evaluation-{safe}"
    return f"evaluation-{uuid4().hex}"


def _job_payload(kwargs: dict[str, Any]) -> dict[str, object]:
    return {
        "role": "backtest",
        "generation": _int_or_none(kwargs.get("generation")),
        "research_run_id": _string_or_none(kwargs.get("research_run_id")),
        "attempt_id": _string_or_none(kwargs.get("attempt_id")),
        "source_path": _path_text(kwargs.get("source_path")),
        "data_path": _path_text(kwargs.get("data_path")),
        "method": _string_or_none(kwargs.get("method")),
        "count": _int_or_none(kwargs.get("count")),
        "seed": _int_or_none(kwargs.get("seed")),
    }


def _path_text(value: object) -> str | None:
    if isinstance(value, Path):
        return str(value)
    return value if isinstance(value, str) else None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
