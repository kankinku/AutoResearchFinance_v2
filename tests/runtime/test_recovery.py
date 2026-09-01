from __future__ import annotations

from datetime import datetime, timedelta, timezone

from runtime.queue import Job, JobQueue, JobStatus


def test_stale_lease_is_requeued_then_exhausted() -> None:
    queue = JobQueue()
    queue.enqueue(Job("job-1", {}, max_attempts=2))
    first = queue.claim(lease_seconds=1)
    assert first is not None and first.lease_until is not None
    now = datetime.now(timezone.utc) + timedelta(seconds=2)

    assert queue.reconcile_stale(now=now) == ("job-1",)
    assert queue.get("job-1").status is JobStatus.QUEUED
    queue.claim(lease_seconds=1)
    assert queue.reconcile_stale(now=now + timedelta(seconds=2)) == ("job-1",)
    assert queue.get("job-1").status is JobStatus.RETRY_EXHAUSTED
