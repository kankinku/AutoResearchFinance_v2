from __future__ import annotations

import time

import pytest

from runtime.queue import Job, JobQueue, JobStatus
from runtime.resource_manager import ResourceManager
from runtime.scheduler import LocalScheduler


def test_queue_has_explicit_idempotent_lifecycle() -> None:
    queue = JobQueue()
    job = Job("job-1", {"value": 2})
    queue.enqueue(job)

    claimed = queue.claim()
    assert claimed.status is JobStatus.RUNNING
    assert claimed.attempt == 1
    queue.succeed("job-1", {"value": 4})
    assert queue.get("job-1").status is JobStatus.SUCCEEDED
    assert queue.get("job-1").result == {"value": 4}
    with pytest.raises(ValueError, match="already exists"):
        queue.enqueue(job)


def test_scheduler_respects_resource_limit_and_records_failure() -> None:
    queue = JobQueue()
    jobs = [Job(f"job-{index}", {"value": index}) for index in range(4)]
    for job in jobs:
        queue.enqueue(job)
    active = 0
    peak = 0

    def handler(job: Job) -> dict[str, int]:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        time.sleep(0.02)
        active -= 1
        if job.job_id == "job-2":
            raise RuntimeError("worker crashed")
        return {"value": job.payload["value"] * 2}

    results = LocalScheduler(queue, ResourceManager(max_concurrency=2)).run(handler)

    assert peak <= 2
    assert results["job-0"].status is JobStatus.SUCCEEDED
    assert results["job-2"].status is JobStatus.FAILED
    assert results["job-2"].error == "worker crashed"
