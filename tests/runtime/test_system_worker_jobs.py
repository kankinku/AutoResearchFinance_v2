from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import runtime.system_worker as worker_module
from core.data.contracts import Bar, DataZone, MarketDataSet
from core.data.parquet import ParquetDataProvider
from runtime.job_protocol import EvaluationJobRequest, EvaluationJobResult
from runtime.persistent_queue import PersistentJobQueue
from runtime.queue import Job, JobStatus
from runtime.system_worker import _run_evaluation_job


def _leased_job(tmp_path: Path, job_id: str = "evaluation-job-1") -> PersistentJobQueue:
    (tmp_path / "strategy.yaml").write_text("fixture", encoding="utf-8")
    (tmp_path / "bars.parquet").write_bytes(b"fixture")
    state = tmp_path / "state"
    queue = PersistentJobQueue(state)
    request = EvaluationJobRequest(
        source_path="strategy.yaml",
        data_path="bars.parquet",
        method="grid",
        count=1,
        seed=0,
        min_trades=0,
        research_run_id="run-1",
        attempt_id="attempt-1",
    )
    queue.enqueue(Job(job_id, request.model_dump(mode="json"), max_attempts=2))
    claimed = queue.claim(job_id=job_id, lease_seconds=30)
    assert claimed is not None
    return queue


def _args(tmp_path: Path, job_id: str = "evaluation-job-1") -> argparse.Namespace:
    return argparse.Namespace(
        job_id=job_id,
        lease_seconds=30.0,
        project_root=str(tmp_path),
    )


def test_evaluation_job_worker_consumes_leased_job_and_records_docker_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    queue = _leased_job(tmp_path)
    captured: dict[str, object] = {}

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "status": "COMPLETED",
            "research_run_id": "run-1",
            "attempt_id": "attempt-1",
        }

    monkeypatch.setattr(worker_module, "run_local_evaluation", fake_evaluation)

    result = _run_evaluation_job(_args(tmp_path), tmp_path / "state")

    assert result == {
        "status": "SUCCEEDED",
        "job_id": "evaluation-job-1",
        "queue_attempt": 1,
    }
    context = captured["execution_context"]
    assert isinstance(context, dict)
    assert context == {
        "job_id": "evaluation-job-1",
        "queue_attempt": 1,
        "max_attempts": 2,
        "execution_mode": "docker_worker",
        "isolated": True,
        "timeout_enforced": True,
        "lease_seconds": 30.0,
    }
    stored = queue.get("evaluation-job-1")
    assert stored.status is JobStatus.SUCCEEDED
    wrapped = EvaluationJobResult.model_validate(stored.result)
    assert wrapped.status == "SUCCEEDED"
    assert wrapped.result is not None
    assert wrapped.result["status"] == "COMPLETED"

    heartbeat = json.loads(
        (tmp_path / "state" / "worker-heartbeats" / "docker-evaluation-job-1.json")
        .read_text(encoding="utf-8")
    )
    assert heartbeat["status"] == "SUCCEEDED"
    assert heartbeat["attempt"] == 1


def test_evaluation_job_worker_records_error_class_without_error_body(
    tmp_path: Path,
    monkeypatch,
) -> None:
    queue = _leased_job(tmp_path)

    def fake_evaluation(**kwargs: object) -> dict[str, object]:
        raise ValueError("private strategy detail")

    monkeypatch.setattr(worker_module, "run_local_evaluation", fake_evaluation)

    with pytest.raises(ValueError, match="private strategy detail"):
        _run_evaluation_job(_args(tmp_path), tmp_path / "state")

    stored = queue.get("evaluation-job-1")
    assert stored.status is JobStatus.FAILED
    assert stored.error == "ValueError"
    assert stored.error_class == "ValueError"
    assert "private strategy detail" not in str(stored)



def test_evaluation_job_worker_runs_through_real_subprocess(tmp_path: Path) -> None:
    strategy = tmp_path / "strategy.yaml"
    strategy.write_text(
        """schema_version: 1
id: subprocess-worker
family: trend
generation: 0
indicators:
  fast: {type: SMA, period: 2}
entry: {logic: AND, conditions: [{op: greater_than, left: close, value: 0}]}
exit: {logic: AND, conditions: [{op: less_than, left: close, value: 0}]}
risk: {stop_loss_pct: 0, take_profit_pct: 0}
""",
        encoding="utf-8",
    )
    timestamps = tuple(
        datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
        for index in range(6)
    )
    bars = tuple(
        Bar(timestamp, "QQQ", 100 + index, 101 + index, 99 + index, 100 + index, 1000)
        for index, timestamp in enumerate(timestamps)
    )
    ParquetDataProvider.write(
        tmp_path / "bars.parquet",
        MarketDataSet("worker-v1", DataZone.DEVELOPMENT, bars),
    )
    state = tmp_path / "state"
    queue = PersistentJobQueue(state)
    request = EvaluationJobRequest(
        source_path="strategy.yaml",
        data_path="bars.parquet",
        count=1,
        min_trades=0,
        min_annual_trades=None,
    )
    queue.enqueue(
        Job(
            "subprocess-job",
            request.model_dump(mode="json"),
            max_attempts=1,
        )
    )
    claimed = queue.claim(job_id="subprocess-job", lease_seconds=60)
    assert claimed is not None

    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "runtime.system_worker",
            "--role",
            "evaluation-job",
            "--state-dir",
            str(state),
            "--project-root",
            str(tmp_path),
            "--job-id",
            "subprocess-job",
            "--lease-seconds",
            "60",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    stored = queue.get("subprocess-job")
    assert stored.status is JobStatus.SUCCEEDED
    wrapped = EvaluationJobResult.model_validate(stored.result)
    assert wrapped.result is not None
    assert wrapped.result["status"] == "COMPLETED"
    assert wrapped.result["candidate_count"] == 1
    events = (
        state / "system" / "research-evidence" / "evidence.sqlite"
    )
    assert events.is_file()
