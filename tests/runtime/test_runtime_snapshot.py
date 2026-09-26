from __future__ import annotations

import json
from pathlib import Path

from memory.evidence_store import EvidenceStore
from runtime.persistent_queue import PersistentJobQueue
from runtime.queue import Job
from runtime.runtime_snapshot import build_runtime_snapshot


def test_runtime_snapshot_aggregates_sanitized_research_jobs_and_evidence(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "research-1",
                "current_generation": 2,
                "current_phase": "BACKTESTING",
                "completed_generations": 1,
                "requested_generations": 3,
                "last_event": "evaluation_started",
                "last_event_at": "2026-09-26T00:00:00+00:00",
                "repair_attempt": 1,
                "repair_attempts_allowed": 3,
                "error": "ValueError: private provider detail",
                "timing_summary": {
                    "backtest": {
                        "count": 1,
                        "total_seconds": 2.5,
                        "p50_seconds": 2.5,
                        "p95_seconds": 2.5,
                        "max_seconds": 2.5,
                        "secret": "do not expose",
                    }
                },
                "generations": [{"intent": {"rationale": "private intent"}}],
            }
        ),
        encoding="utf-8",
    )
    queue = PersistentJobQueue(state)
    queue.enqueue(
        Job(
            "evaluation-1",
            {"managed_run_id": "managed-1", "secret": "private"},
            max_attempts=2,
        )
    )
    assert queue.claim(job_id="evaluation-1", lease_seconds=30) is not None
    (system / "evaluation-jobs.jsonl").write_text(
        json.dumps(
            {
                "managed_run_id": "managed-1",
                "job_id": "evaluation-0",
                "status": "TIMED_OUT",
                "queue_attempt": 1,
                "max_attempts": 2,
                "error_class": "TimeoutError",
                "execution_mode": "docker_worker",
                "isolated": True,
                "timeout_enforced": True,
                "research_run_id": "research-1",
                "attempt_id": "attempt-1",
                "generation": 1,
                "error": "private exception body",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = EvidenceStore(state)
    store.append(
        "run",
        "run:research-1",
        {
            "research_run_id": "research-1",
            "requested_generations": 3,
            "seed": 0,
        },
    )
    store.append(
        "end",
        "end:research-1",
        {"research_run_id": "research-1", "status": "COMPLETED"},
    )

    snapshot = build_runtime_snapshot(state, managed_run_id="managed-1")

    research = snapshot["research"]
    assert research["research_run_id"] == "research-1"
    assert research["current_generation"] == 2
    assert research["current_phase"] == "BACKTESTING"
    assert research["error_class"] == "ValueError"
    assert "generations" not in research
    assert "private provider detail" not in json.dumps(snapshot)

    evaluation = snapshot["evaluation"]
    assert evaluation["counts"]["RUNNING"] == 1
    assert evaluation["active_jobs"][0]["job_id"] == "evaluation-1"
    assert evaluation["latest_job"]["status"] == "TIMED_OUT"
    assert evaluation["latest_job"]["error_class"] == "TimeoutError"
    assert "private exception body" not in json.dumps(snapshot)

    evidence = snapshot["evidence"]
    assert evidence == {
        "status": "COMPLETED",
        "research_run_id": "research-1",
        "event_count": 2,
        "last_event_kind": "end",
        "closed": True,
    }
    assert snapshot["orders_enabled"] is False


def test_runtime_snapshot_is_safe_when_no_runtime_state_exists(tmp_path: Path) -> None:
    snapshot = build_runtime_snapshot(tmp_path / "state", managed_run_id=None)

    assert snapshot["research"]["status"] == "NOT_STARTED"
    assert snapshot["evaluation"]["counts"] == {}
    assert snapshot["evaluation"]["latest_job"] is None
    assert snapshot["evidence"]["status"] == "NOT_LINKED"
    assert snapshot["orders_enabled"] is False


def test_runtime_snapshot_filters_jobs_by_managed_run(tmp_path: Path) -> None:
    state = tmp_path / "state"
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("owned", {"managed_run_id": "run-a"}, max_attempts=1))
    queue.enqueue(Job("other", {"managed_run_id": "run-b"}, max_attempts=1))
    assert queue.claim(job_id="owned", lease_seconds=30) is not None
    assert queue.claim(job_id="other", lease_seconds=30) is not None

    snapshot = build_runtime_snapshot(state, managed_run_id="run-a")

    assert snapshot["evaluation"]["counts"] == {"RUNNING": 1}
    assert [job["job_id"] for job in snapshot["evaluation"]["active_jobs"]] == [
        "owned"
    ]
