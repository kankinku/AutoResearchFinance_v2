from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from runtime.heartbeat import WorkerHeartbeatStore
from runtime.queue import Job, JobQueue
from runtime.resource_manager import ResourceManager
from runtime.scheduler import LocalScheduler


def test_heartbeat_store_writes_sanitized_worker_record(tmp_path: Path) -> None:
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    store = WorkerHeartbeatStore(tmp_path, clock=lambda: now)

    store.record("worker-1", job_id="job-1", role="backtest", status="RUNNING", attempt=1)

    payload = json.loads((tmp_path / "worker-1.json").read_text(encoding="utf-8"))
    assert payload == {
        "worker_id": "worker-1",
        "job_id": "job-1",
        "role": "backtest",
        "status": "RUNNING",
        "last_heartbeat": "2026-09-01T12:00:00+00:00",
        "attempt": 1,
    }


def test_scheduler_updates_heartbeat_for_parallel_job(tmp_path: Path) -> None:
    queue = JobQueue()
    queue.enqueue(Job("job-1", {"role": "backtest"}))
    scheduler = LocalScheduler(
        queue,
        ResourceManager(max_concurrency=1),
        heartbeat_store=WorkerHeartbeatStore(tmp_path),
    )

    scheduler.run(lambda job: {"job": job.job_id})

    payload = json.loads((tmp_path / "local-job-1.json").read_text(encoding="utf-8"))
    assert payload["status"] == "SUCCEEDED"
    assert payload["job_id"] == "job-1"



def test_heartbeat_store_constructor_is_side_effect_free(tmp_path: Path) -> None:
    root = tmp_path / "heartbeats"

    WorkerHeartbeatStore(root)

    assert not root.exists()
