from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from research.policy import load_policy
from runtime.docker_evaluation import DockerEvaluationRunner, DockerWorkerTimeout
from runtime.heartbeat import WorkerHeartbeatStore
from runtime.job_protocol import EvaluationJobRequest, EvaluationJobResult
from runtime.persistent_queue import PersistentJobQueue
from runtime.queue import Job, JobQueue, JobStatus
from runtime.resource_manager import ResourceManager
from runtime.scheduler import LocalScheduler

EvaluationCallable = Callable[..., dict[str, object]]
ExecutionMode = Literal["local_scheduler", "docker_worker"]

_RETRYABLE_ERRORS = {
    "BrokenPipeError",
    "ConnectionError",
    "TimeoutError",
    "WorkerProcessError",
}



def is_retryable_error(error_class: str | None) -> bool:
    return error_class in _RETRYABLE_ERRORS


class EvaluationExecutionError(RuntimeError):
    """Raised when the scheduled evaluation worker cannot complete a job."""


class QueuedEvaluationExecutor:
    """Route canonical evaluation through a local or Docker worker boundary."""

    def __init__(
        self,
        state_dir: Path,
        *,
        project_root: Path | None = None,
        execution_mode: ExecutionMode | None = None,
        docker_image: str | None = None,
        docker_runner: DockerEvaluationRunner | None = None,
        max_concurrency: int | None = None,
        max_retries: int | None = None,
        lease_seconds: float | None = None,
        managed_run_id: str | None = None,
    ) -> None:
        policy = load_policy(
            Path(__file__).resolve().parents[1] / "research" / "policy.yaml"
        ).runtime
        self.state_dir = state_dir.resolve()
        self.project_root = project_root.resolve() if project_root is not None else None
        self.managed_run_id = managed_run_id
        configured_mode = execution_mode or os.environ.get(
            "QUANT_EVALUATION_EXECUTION", "local_scheduler"
        )
        if configured_mode not in {"local_scheduler", "docker_worker"}:
            raise ValueError("unsupported evaluation execution mode")
        self.execution_mode = cast(ExecutionMode, configured_mode)
        self.docker_image = docker_image or os.environ.get(
            "QUANT_EVALUATION_DOCKER_IMAGE",
            "quant-autoresearch-worker:local",
        )
        self.max_concurrency = (
            policy.max_concurrency if max_concurrency is None else max_concurrency
        )
        self.max_retries = policy.max_retries if max_retries is None else max_retries
        self.lease_seconds = float(
            policy.job_timeout_seconds if lease_seconds is None else lease_seconds
        )
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if self.execution_mode == "docker_worker" and self.project_root is None:
            raise ValueError("docker evaluation requires project_root")
        self.resources = ResourceManager(max_concurrency=self.max_concurrency)
        self._log_lock = threading.Lock()
        self.heartbeat_store = WorkerHeartbeatStore(
            self.state_dir / "worker-heartbeats"
        )
        self.docker_runner = docker_runner or (
            DockerEvaluationRunner(image=self.docker_image)
            if self.execution_mode == "docker_worker"
            else None
        )

    def run(
        self,
        evaluator: EvaluationCallable,
        **kwargs: Any,
    ) -> dict[str, object]:
        if self.execution_mode == "docker_worker":
            return self._run_docker(evaluator, kwargs)
        return self._run_local(evaluator, kwargs)

    def _run_local(
        self,
        evaluator: EvaluationCallable,
        kwargs: dict[str, Any],
    ) -> dict[str, object]:
        queue = JobQueue()
        job_id = _job_id(kwargs.get("attempt_id"))
        payload_kwargs = dict(kwargs)
        payload_kwargs["managed_run_id"] = self.managed_run_id
        job = Job(
            job_id,
            _job_payload(payload_kwargs),
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
                call_kwargs["execution_context"] = self._execution_context(current_job)
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
                and is_retryable_error(current.error_class)
                and current.attempt < current.max_attempts
            ):
                self._record_attempt(current, kwargs, None)
                queue.retry_failed(job_id)
                continue
            if (
                current.status is JobStatus.FAILED
                and is_retryable_error(current.error_class)
                and current.attempt >= current.max_attempts
            ):
                queue.retry_failed(job_id)
            self._record_attempt(current, kwargs, None)
            error = current.error or "evaluation worker failed"
            raise EvaluationExecutionError(error)

    def _run_docker(
        self,
        evaluator: EvaluationCallable,
        kwargs: dict[str, Any],
    ) -> dict[str, object]:
        if not _is_canonical_evaluator(evaluator):
            raise EvaluationExecutionError(
                "docker evaluation only supports run_local_evaluation"
            )
        if self.project_root is None or self.docker_runner is None:
            raise EvaluationExecutionError("docker evaluation is not configured")
        queue = PersistentJobQueue(self.state_dir)
        queue.reconcile_stale()
        job_id = _job_id(kwargs.get("attempt_id"))
        request_kwargs = dict(kwargs)
        request_kwargs["managed_run_id"] = self.managed_run_id
        request = EvaluationJobRequest.from_evaluation_kwargs(
            self.project_root,
            request_kwargs,
        )
        queue.enqueue(
            Job(
                job_id,
                request.model_dump(mode="json"),
                max_attempts=self.max_retries + 1,
            )
        )

        while True:
            claimed = queue.claim(job_id=job_id, lease_seconds=self.lease_seconds)
            if claimed is None:
                current = queue.get(job_id)
                if current.status is JobStatus.SUCCEEDED:
                    return self._docker_result(current, kwargs)
                raise EvaluationExecutionError(
                    f"docker evaluation job is not claimable: {current.status.value}"
                )
            self.resources.acquire()
            try:
                try:
                    self.docker_runner.run(
                        project_root=self.project_root,
                        state_dir=self.state_dir,
                        job_id=job_id,
                        queue_attempt=claimed.attempt,
                        lease_seconds=self.lease_seconds,
                        timeout=self.lease_seconds,
                    )
                except DockerWorkerTimeout:
                    current = queue.get(job_id)
                    if current.status is JobStatus.SUCCEEDED:
                        return self._docker_result(current, kwargs)
                    if current.status is JobStatus.RUNNING:
                        queue.timeout(job_id, error_class="TimeoutError")
                else:
                    current = queue.get(job_id)
                    if current.status is JobStatus.RUNNING:
                        queue.abort_running(job_id, error_class="WorkerProcessError")
            finally:
                self.resources.release()

            current = queue.get(job_id)
            if current.status is JobStatus.SUCCEEDED:
                return self._docker_result(current, kwargs)
            if (
                current.status in {JobStatus.FAILED, JobStatus.TIMED_OUT}
                and is_retryable_error(current.error_class)
            ):
                if current.attempt < current.max_attempts:
                    self._record_attempt(current, kwargs, None)
                    queue.retry_terminal(job_id)
                    continue
                queue.retry_terminal(job_id)
                current = queue.get(job_id)
            self._record_attempt(current, kwargs, None)
            raise EvaluationExecutionError(
                current.error_class or current.error or "docker evaluation worker failed"
            )

    def _docker_result(
        self,
        current: Job,
        kwargs: dict[str, Any],
    ) -> dict[str, object]:
        worker_payload = _worker_result_payload(current)
        result = EvaluationJobResult.model_validate(worker_payload)
        if result.status != "SUCCEEDED" or result.result is None:
            raise EvaluationExecutionError("docker worker returned an invalid result")
        self._record_attempt(current, kwargs, result.result)
        return result.result

    def _execution_context(self, job: Job) -> dict[str, object]:
        docker = self.execution_mode == "docker_worker"
        context: dict[str, object] = {
            "job_id": job.job_id,
            "queue_attempt": job.attempt,
            "max_attempts": job.max_attempts,
            "execution_mode": self.execution_mode,
            "isolated": docker,
            "timeout_enforced": docker,
            "lease_seconds": self.lease_seconds,
        }
        if self.managed_run_id is not None:
            context["managed_run_id"] = self.managed_run_id
        return context

    def _record_attempt(
        self,
        job: Job,
        kwargs: dict[str, Any],
        result: dict[str, object] | None,
    ) -> None:
        research_run_id = _string_or_none(kwargs.get("research_run_id"))
        attempt_id = _string_or_none(kwargs.get("attempt_id"))
        if result is not None:
            research_run_id = research_run_id or _string_or_none(
                result.get("research_run_id")
            )
            attempt_id = attempt_id or _string_or_none(result.get("attempt_id"))
        docker = self.execution_mode == "docker_worker"
        payload = {
            "job_id": job.job_id,
            "research_run_id": research_run_id,
            "attempt_id": attempt_id,
            "generation": _int_or_none(kwargs.get("generation")),
            "status": job.status.value,
            "queue_attempt": job.attempt,
            "max_attempts": job.max_attempts,
            "error_class": job.error_class,
            "execution_mode": self.execution_mode,
            "isolated": docker,
            "timeout_enforced": docker,
            "lease_seconds": self.lease_seconds,
        }
        if self.managed_run_id is not None:
            payload["managed_run_id"] = self.managed_run_id
        target = self.state_dir / "system" / "evaluation-jobs.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._log_lock:
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _worker_result_payload(job: Job) -> dict[str, object]:
    if job.result is None:
        raise EvaluationExecutionError("docker worker returned no result")
    return {str(key): value for key, value in job.result.items()}


def _is_canonical_evaluator(evaluator: EvaluationCallable) -> bool:
    return (
        getattr(evaluator, "__module__", "") == "orchestration.evaluation_runner"
        and getattr(evaluator, "__name__", "") == "run_local_evaluation"
    )


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
