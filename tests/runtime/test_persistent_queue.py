from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.persistent_queue import PersistentJobQueue
from runtime.queue import Job, JobStatus


def test_persistent_queue_is_shared_across_processes(tmp_path: Path) -> None:
    state = tmp_path / "state"
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("job-1", {"value": 3}, max_attempts=2))
    repo_root = Path(__file__).resolve().parents[2]
    code = (
        "from pathlib import Path;"
        "from runtime.persistent_queue import PersistentJobQueue;"
        f"q=PersistentJobQueue(Path({str(state)!r}));"
        "j=q.claim(job_id='job-1', lease_seconds=30);"
        "assert j is not None and j.attempt == 1;"
        "q.succeed('job-1', {'value': j.payload['value'] * 2})"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    persisted = queue.get("job-1")
    assert persisted.status is JobStatus.SUCCEEDED
    assert persisted.attempt == 1
    assert persisted.result == {"value": 6}


def test_persistent_queue_reconciles_expired_cross_process_lease(tmp_path: Path) -> None:
    queue = PersistentJobQueue(tmp_path / "state")
    queue.enqueue(Job("job-1", {}, max_attempts=2))
    claimed = queue.claim(job_id="job-1", lease_seconds=1)
    assert claimed is not None and claimed.lease_until is not None

    future = datetime.now(timezone.utc) + timedelta(seconds=2)
    assert queue.reconcile_stale(now=future) == ("job-1",)
    assert queue.get("job-1").status is JobStatus.QUEUED

    second = queue.claim(job_id="job-1", lease_seconds=1)
    assert second is not None and second.attempt == 2
    assert queue.reconcile_stale(now=future + timedelta(seconds=2)) == ("job-1",)
    exhausted = queue.get("job-1")
    assert exhausted.status is JobStatus.RETRY_EXHAUSTED
    assert exhausted.error_class == "LeaseExpired"


def test_persistent_queue_retries_terminal_timeout_then_exhausts(tmp_path: Path) -> None:
    queue = PersistentJobQueue(tmp_path / "state")
    queue.enqueue(Job("job-1", {}, max_attempts=2))

    first = queue.claim(job_id="job-1", lease_seconds=30)
    assert first is not None
    queue.timeout("job-1")
    queue.retry_terminal("job-1")
    assert queue.get("job-1").status is JobStatus.QUEUED

    second = queue.claim(job_id="job-1", lease_seconds=30)
    assert second is not None and second.attempt == 2
    queue.timeout("job-1")
    queue.retry_terminal("job-1")
    exhausted = queue.get("job-1")
    assert exhausted.status is JobStatus.RETRY_EXHAUSTED
    assert exhausted.error_class == "TimeoutError"
