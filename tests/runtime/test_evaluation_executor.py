from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.evaluation_executor import (
    EvaluationExecutionError,
    QueuedEvaluationExecutor,
)


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
