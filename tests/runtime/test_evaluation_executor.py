from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration.evaluation_runner import run_local_evaluation
from runtime.docker_evaluation import DockerWorkerTimeout
from runtime.evaluation_executor import (
    EvaluationExecutionError,
    QueuedEvaluationExecutor,
)
from runtime.job_protocol import EvaluationJobResult
from runtime.persistent_queue import PersistentJobQueue


def _job_records(state_dir: Path) -> list[dict[str, object]]:
    path = state_dir / "system" / "evaluation-jobs.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_executor_routes_evaluation_through_scheduler_and_heartbeat(tmp_path: Path) -> None:
    state = tmp_path / "state"
    captured: dict[str, object] = {}

    def evaluator(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "status": "COMPLETED",
            "research_run_id": "run-1",
            "attempt_id": "attempt-1",
        }

    result = QueuedEvaluationExecutor(
        state,
        max_concurrency=1,
        max_retries=0,
        lease_seconds=10,
    ).run(evaluator, generation=2, seed=7)

    assert result["status"] == "COMPLETED"
    context = captured["execution_context"]
    assert isinstance(context, dict)
    assert context["execution_mode"] == "local_scheduler"
    assert context["isolated"] is False
    assert context["timeout_enforced"] is False
    assert context["queue_attempt"] == 1

    records = _job_records(state)
    assert records == [
        {
            "attempt_id": "attempt-1",
            "error_class": None,
            "execution_mode": "local_scheduler",
            "generation": 2,
            "isolated": False,
            "job_id": records[0]["job_id"],
            "lease_seconds": 10.0,
            "max_attempts": 1,
            "queue_attempt": 1,
            "research_run_id": "run-1",
            "status": "SUCCEEDED",
            "timeout_enforced": False,
        }
    ]
    heartbeat = json.loads(
        next((state / "worker-heartbeats").glob("local-evaluation-*.json")).read_text(
            encoding="utf-8"
        )
    )
    assert heartbeat["status"] == "SUCCEEDED"
    assert heartbeat["attempt"] == 1
    assert heartbeat["role"] == "backtest"


def test_executor_retries_only_transient_worker_failures(tmp_path: Path) -> None:
    state = tmp_path / "state"
    calls = 0

    def evaluator(**kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("transient timeout")
        return {"status": "COMPLETED"}

    result = QueuedEvaluationExecutor(
        state,
        max_concurrency=1,
        max_retries=1,
        lease_seconds=5,
    ).run(evaluator, attempt_id="attempt-retry")

    assert result == {"status": "COMPLETED"}
    assert calls == 2
    records = _job_records(state)
    assert [record["status"] for record in records] == ["FAILED", "SUCCEEDED"]
    assert [record["queue_attempt"] for record in records] == [1, 2]
    assert records[0]["error_class"] == "TimeoutError"


def test_executor_does_not_retry_deterministic_validation_failure(tmp_path: Path) -> None:
    state = tmp_path / "state"
    calls = 0

    def evaluator(**kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise ValueError("invalid strategy")

    with pytest.raises(EvaluationExecutionError, match="invalid strategy"):
        QueuedEvaluationExecutor(
            state,
            max_concurrency=1,
            max_retries=2,
            lease_seconds=5,
        ).run(evaluator, attempt_id="attempt-invalid")

    assert calls == 1
    records = _job_records(state)
    assert len(records) == 1
    assert records[0]["status"] == "FAILED"
    assert records[0]["error_class"] == "ValueError"


def test_executor_marks_retry_exhaustion_without_persisting_error_text(tmp_path: Path) -> None:
    state = tmp_path / "state"
    calls = 0

    def evaluator(**kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise ConnectionError("private upstream detail")

    with pytest.raises(EvaluationExecutionError, match="maximum attempts"):
        QueuedEvaluationExecutor(
            state,
            max_concurrency=1,
            max_retries=1,
            lease_seconds=5,
        ).run(evaluator, attempt_id="attempt-exhausted")

    assert calls == 2
    records = _job_records(state)
    assert [record["status"] for record in records] == ["FAILED", "RETRY_EXHAUSTED"]
    serialized = json.dumps(records)
    assert "private upstream detail" not in serialized



def _docker_inputs(root: Path) -> None:
    (root / "strategy.yaml").write_text("fixture", encoding="utf-8")
    (root / "bars.parquet").write_bytes(b"fixture")
    (root / "state").mkdir(exist_ok=True)


def test_executor_docker_backend_consumes_persistent_job(tmp_path: Path) -> None:
    _docker_inputs(tmp_path)
    calls = 0

    class FakeDockerRunner:
        def run(self, **kwargs: object) -> SimpleNamespace:
            nonlocal calls
            calls += 1
            state_dir = kwargs["state_dir"]
            job_id = kwargs["job_id"]
            assert isinstance(state_dir, Path)
            assert isinstance(job_id, str)
            queue = PersistentJobQueue(state_dir)
            job = queue.get(job_id)
            wrapped = EvaluationJobResult(
                job_id=job_id,
                queue_attempt=job.attempt,
                status="SUCCEEDED",
                result={
                    "status": "COMPLETED",
                    "research_run_id": "run-docker",
                    "attempt_id": "attempt-docker",
                },
            )
            queue.succeed(job_id, wrapped.model_dump(mode="json"))
            return SimpleNamespace(returncode=0)

    result = QueuedEvaluationExecutor(
        tmp_path / "state",
        project_root=tmp_path,
        execution_mode="docker_worker",
        docker_runner=FakeDockerRunner(),  # type: ignore[arg-type]
        max_retries=1,
        lease_seconds=10,
    ).run(
        run_local_evaluation,
        source_path="strategy.yaml",
        data_path="bars.parquet",
        generation=1,
        research_run_id="run-docker",
        attempt_id="attempt-docker",
    )

    assert result["status"] == "COMPLETED"
    assert calls == 1
    records = _job_records(tmp_path / "state")
    assert records[-1]["execution_mode"] == "docker_worker"
    assert records[-1]["isolated"] is True
    assert records[-1]["timeout_enforced"] is True
    assert records[-1]["status"] == "SUCCEEDED"


def test_executor_docker_timeout_requeues_and_succeeds_on_retry(tmp_path: Path) -> None:
    _docker_inputs(tmp_path)
    calls = 0

    class FakeDockerRunner:
        def run(self, **kwargs: object) -> SimpleNamespace:
            nonlocal calls
            calls += 1
            state_dir = kwargs["state_dir"]
            job_id = kwargs["job_id"]
            assert isinstance(state_dir, Path)
            assert isinstance(job_id, str)
            if calls == 1:
                raise DockerWorkerTimeout("timeout")
            queue = PersistentJobQueue(state_dir)
            job = queue.get(job_id)
            queue.succeed(
                job_id,
                EvaluationJobResult(
                    job_id=job_id,
                    queue_attempt=job.attempt,
                    status="SUCCEEDED",
                    result={"status": "COMPLETED"},
                ).model_dump(mode="json"),
            )
            return SimpleNamespace(returncode=0)

    result = QueuedEvaluationExecutor(
        tmp_path / "state",
        project_root=tmp_path,
        execution_mode="docker_worker",
        docker_runner=FakeDockerRunner(),  # type: ignore[arg-type]
        max_retries=1,
        lease_seconds=2,
    ).run(
        run_local_evaluation,
        source_path="strategy.yaml",
        data_path="bars.parquet",
        attempt_id="attempt-timeout",
    )

    assert result == {"status": "COMPLETED"}
    assert calls == 2
    records = _job_records(tmp_path / "state")
    assert [record["status"] for record in records[-2:]] == ["TIMED_OUT", "SUCCEEDED"]
    assert [record["queue_attempt"] for record in records[-2:]] == [1, 2]


def test_executor_docker_does_not_retry_deterministic_worker_failure(
    tmp_path: Path,
) -> None:
    _docker_inputs(tmp_path)
    calls = 0

    class FakeDockerRunner:
        def run(self, **kwargs: object) -> SimpleNamespace:
            nonlocal calls
            calls += 1
            state_dir = kwargs["state_dir"]
            job_id = kwargs["job_id"]
            assert isinstance(state_dir, Path)
            assert isinstance(job_id, str)
            PersistentJobQueue(state_dir).fail(
                job_id,
                "ValueError",
                error_class="ValueError",
            )
            return SimpleNamespace(returncode=2)

    with pytest.raises(EvaluationExecutionError, match="ValueError"):
        QueuedEvaluationExecutor(
            tmp_path / "state",
            project_root=tmp_path,
            execution_mode="docker_worker",
            docker_runner=FakeDockerRunner(),  # type: ignore[arg-type]
            max_retries=2,
            lease_seconds=2,
        ).run(
            run_local_evaluation,
            source_path="strategy.yaml",
            data_path="bars.parquet",
            attempt_id="attempt-invalid-docker",
        )

    assert calls == 1



def test_executor_docker_process_exit_without_queue_result_is_recovered(
    tmp_path: Path,
) -> None:
    _docker_inputs(tmp_path)
    calls = 0

    class FakeDockerRunner:
        def run(self, **kwargs: object) -> SimpleNamespace:
            nonlocal calls
            calls += 1
            state_dir = kwargs["state_dir"]
            job_id = kwargs["job_id"]
            assert isinstance(state_dir, Path)
            assert isinstance(job_id, str)
            if calls == 1:
                return SimpleNamespace(returncode=0)
            queue = PersistentJobQueue(state_dir)
            job = queue.get(job_id)
            queue.succeed(
                job_id,
                EvaluationJobResult(
                    job_id=job_id,
                    queue_attempt=job.attempt,
                    status="SUCCEEDED",
                    result={"status": "COMPLETED"},
                ).model_dump(mode="json"),
            )
            return SimpleNamespace(returncode=0)

    result = QueuedEvaluationExecutor(
        tmp_path / "state",
        project_root=tmp_path,
        execution_mode="docker_worker",
        docker_runner=FakeDockerRunner(),  # type: ignore[arg-type]
        max_retries=1,
        lease_seconds=2,
    ).run(
        run_local_evaluation,
        source_path="strategy.yaml",
        data_path="bars.parquet",
        attempt_id="attempt-orphan-process",
    )

    assert result == {"status": "COMPLETED"}
    assert calls == 2
    records = _job_records(tmp_path / "state")
    assert records[-2]["status"] == "FAILED"
    assert records[-2]["error_class"] == "WorkerProcessError"
    assert records[-1]["status"] == "SUCCEEDED"


def test_executor_docker_timeout_exhaustion_has_single_final_terminal_record(
    tmp_path: Path,
) -> None:
    _docker_inputs(tmp_path)

    class FakeDockerRunner:
        def run(self, **kwargs: object) -> SimpleNamespace:
            raise DockerWorkerTimeout("timeout")

    with pytest.raises(EvaluationExecutionError, match="TimeoutError"):
        QueuedEvaluationExecutor(
            tmp_path / "state",
            project_root=tmp_path,
            execution_mode="docker_worker",
            docker_runner=FakeDockerRunner(),  # type: ignore[arg-type]
            max_retries=1,
            lease_seconds=2,
        ).run(
            run_local_evaluation,
            source_path="strategy.yaml",
            data_path="bars.parquet",
            attempt_id="attempt-timeout-exhausted",
        )

    records = _job_records(tmp_path / "state")
    assert [record["status"] for record in records[-2:]] == [
        "TIMED_OUT",
        "RETRY_EXHAUSTED",
    ]
    assert [record["queue_attempt"] for record in records[-2:]] == [1, 2]



def test_executor_records_managed_run_identity_in_local_context(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def evaluator(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "COMPLETED"}

    QueuedEvaluationExecutor(
        tmp_path / "state",
        managed_run_id="managed-run-1",
        max_retries=0,
    ).run(evaluator, generation=1)

    context = captured["execution_context"]
    assert isinstance(context, dict)
    assert context["managed_run_id"] == "managed-run-1"
    records = _job_records(tmp_path / "state")
    assert records[-1]["managed_run_id"] == "managed-run-1"


def test_executor_persists_managed_run_identity_in_docker_job(tmp_path: Path) -> None:
    _docker_inputs(tmp_path)

    class FakeDockerRunner:
        def run(self, **kwargs: object) -> SimpleNamespace:
            state_dir = kwargs["state_dir"]
            job_id = kwargs["job_id"]
            assert isinstance(state_dir, Path)
            assert isinstance(job_id, str)
            queue = PersistentJobQueue(state_dir)
            job = queue.get(job_id)
            assert job.payload["managed_run_id"] == "managed-run-1"
            queue.succeed(
                job_id,
                EvaluationJobResult(
                    job_id=job_id,
                    queue_attempt=job.attempt,
                    status="SUCCEEDED",
                    result={"status": "COMPLETED"},
                ).model_dump(mode="json"),
            )
            return SimpleNamespace(returncode=0)

    result = QueuedEvaluationExecutor(
        tmp_path / "state",
        project_root=tmp_path,
        execution_mode="docker_worker",
        docker_runner=FakeDockerRunner(),  # type: ignore[arg-type]
        managed_run_id="managed-run-1",
        max_retries=0,
    ).run(
        run_local_evaluation,
        source_path="strategy.yaml",
        data_path="bars.parquet",
        attempt_id="managed-docker",
    )

    assert result == {"status": "COMPLETED"}
    assert _job_records(tmp_path / "state")[-1]["managed_run_id"] == "managed-run-1"
