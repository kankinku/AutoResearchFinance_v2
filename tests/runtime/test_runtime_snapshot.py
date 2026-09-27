from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from memory.evidence_knowledge import sync_knowledge
from memory.evidence_store import EvidenceStore
from runtime.persistent_queue import PersistentJobQueue
from runtime.queue import Job
from runtime.runtime_contracts import RuntimeSnapshot
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
    assert evidence["status"] == "COMPLETED"
    assert evidence["link_status"] == "LINKED"
    assert evidence["integrity_status"] == "VERIFIED"
    assert evidence["research_run_id"] == "research-1"
    assert evidence["event_count"] == 2
    assert evidence["last_event_kind"] == "end"
    assert evidence["terminal_status"] == "COMPLETED"
    assert evidence["closed"] is True
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



def test_runtime_snapshot_uses_typed_contract_and_adds_operational_views(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "research-2",
                "current_generation": 2,
                "current_phase": "FINALIZING",
                "completed_generations": 1,
                "requested_generations": 3,
                "generations": [
                    {
                        "generation": 2,
                        "intent_status": "REPAIRED",
                        "intent": {
                            "mode": "parameter",
                            "parent_ids": ["parent-1"],
                            "operations": [{"op": "set_parameter"}],
                            "rationale": "must not be exposed",
                        },
                        "operations": [{"op": "set_parameter", "path": "indicators.fast.period"}],
                        "repair_attempts": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (state / "knowledge.json").write_text(
        json.dumps(
            {
                "known_good": [{"id": 1}],
                "known_bad": [{"id": 2}, {"id": 3}],
                "unexplored": [],
                "interactions": [{"id": 4}],
            }
        ),
        encoding="utf-8",
    )
    (state / "champion.json").write_text(
        json.dumps(
            {
                "status": "CHAMPION",
                "champion": {
                    "status": "CHAMPION",
                    "champion_hash": "abc123",
                    "score": 1.25,
                },
            }
        ),
        encoding="utf-8",
    )
    llm_dir = state / "llm"
    llm_dir.mkdir()
    (llm_dir / "status.json").write_text(
        json.dumps(
            {
                "provider": "codex_exec",
                "status": "ONLINE",
                "last_result": "PROPOSED",
                "last_call_at": "2026-09-27T00:00:00+00:00",
                "operation": "propose",
            }
        ),
        encoding="utf-8",
    )
    heartbeat_dir = state / "worker-heartbeats"
    heartbeat_dir.mkdir()
    (heartbeat_dir / "eval-1.json").write_text(
        json.dumps(
            {
                "worker_id": "eval-1",
                "job_id": "job-1",
                "role": "evaluation",
                "status": "FAILED",
                "last_heartbeat": "2026-09-27T00:00:00+00:00",
                "attempt": 2,
                "error": "ValueError: private worker detail",
            }
        ),
        encoding="utf-8",
    )
    (system / "recovery-events.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-09-27T00:01:00+00:00",
                "event": "RESTARTED",
                "managed_run_id": "managed-old",
                "orders_enabled": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = build_runtime_snapshot(
        state,
        managed_run_id="managed-2",
        system_state={
            "status": "RUNNING",
            "managed_run_id": "managed-2",
            "started_at": "2026-09-27T00:00:00+00:00",
            "evaluation_execution": "local_scheduler",
            "components": [
                {
                    "id": "research_worker",
                    "status": "RUNNING",
                    "alive": True,
                    "pid": 123,
                    "identity_markers": ["private-marker"],
                }
            ],
        },
    )
    snapshot = RuntimeSnapshot.model_validate(payload)

    assert snapshot.schema_version == 2
    assert snapshot.system.status == "RUNNING"
    assert snapshot.system.managed_run_id == "managed-2"
    assert snapshot.system.components[0].pid == 123
    assert snapshot.research.current_intent.status == "AVAILABLE"
    assert snapshot.research.current_intent.mode == "parameter"
    assert snapshot.research.current_intent.parent_ids == ["parent-1"]
    assert snapshot.research.current_intent.operation_count == 1
    assert snapshot.research.current_intent.repair_attempts == 1
    assert snapshot.llm.status == "ONLINE"
    assert snapshot.knowledge.known_good_count == 1
    assert snapshot.knowledge.known_bad_count == 2
    assert snapshot.strategy_state.champion_hash == "abc123"
    assert snapshot.strategy_state.frontier_status == "NOT_CONNECTED"
    assert snapshot.strategy_state.rescue_status == "NOT_CONNECTED"
    assert snapshot.recovery.last_event == "RESTARTED"
    assert snapshot.workers[0].error_class == "ValueError"
    serialized = json.dumps(payload)
    assert "must not be exposed" not in serialized
    assert "private worker detail" not in serialized
    assert "private-marker" not in serialized


def test_runtime_snapshot_read_does_not_create_state(tmp_path: Path) -> None:
    state = tmp_path / "missing-state"

    payload = build_runtime_snapshot(state, managed_run_id=None)

    assert payload["research"]["status"] == "NOT_STARTED"
    assert payload["evaluation"]["counts"] == {}
    assert not state.exists()


def test_runtime_snapshot_does_not_treat_initialized_frontier_as_live_state(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "frontier.json").write_text(
        '{"schema_version":1,"families":{"trend":[{"id":"legacy"}]}}',
        encoding="utf-8",
    )
    (state / "rescue_pool.json").write_text(
        '{"schema_version":1,"entries":[{"id":"legacy"}]}',
        encoding="utf-8",
    )

    payload = build_runtime_snapshot(state, managed_run_id=None)

    assert payload["strategy_state"]["frontier_status"] == "NOT_CONNECTED"
    assert payload["strategy_state"]["rescue_status"] == "NOT_CONNECTED"



def test_research_snapshot_reports_precise_generation_progress(tmp_path: Path) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "COMPLETED_WITH_ERRORS",
                "research_run_id": "research-progress",
                "current_generation": 3,
                "current_phase": "COMPLETED",
                "completed_generations": 3,
                "requested_generations": 3,
                "phase_started_at": (now - timedelta(seconds=5)).isoformat(),
                "last_event": "run_completed",
                "last_event_at": (now - timedelta(seconds=4)).isoformat(),
                "generations": [
                    {"generation": 1, "status": "REJECT"},
                    {"generation": 2, "status": "FALLBACK"},
                    {"generation": 3, "status": "DEGRADED"},
                ],
            }
        ),
        encoding="utf-8",
    )

    research = build_runtime_snapshot(state, managed_run_id=None)["research"]

    assert research["completion_percent"] == 100.0
    assert research["last_completed_generation"] == 3
    assert research["last_completed_status"] == "DEGRADED"
    assert research["last_non_degraded_generation"] == 2
    assert research["phase_age_seconds"] is not None
    assert research["last_event_age_seconds"] is not None
    assert research["stale_after_seconds"] is None
    assert research["is_stale"] is False
    assert research["consistency_status"] == "OK"
    assert research["consistency_issues"] == []


def test_research_snapshot_marks_stale_backtest_after_conservative_timeout(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(seconds=1900)).isoformat()
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "research-stale",
                "current_generation": 2,
                "current_phase": "BACKTESTING",
                "completed_generations": 1,
                "requested_generations": 4,
                "phase_started_at": old,
                "last_event": "evaluation_started",
                "last_event_at": old,
                "generations": [{"generation": 1, "status": "REJECT"}],
            }
        ),
        encoding="utf-8",
    )

    research = build_runtime_snapshot(state, managed_run_id=None)["research"]

    assert research["completion_percent"] == 25.0
    assert research["stale_after_seconds"] == 1800.0
    assert research["last_event_age_seconds"] >= 1800.0
    assert research["is_stale"] is True
    assert research["consistency_status"] == "OK"


def test_research_snapshot_does_not_mark_valid_long_proposal_stale(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(seconds=550)).isoformat()
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "research-proposal",
                "current_generation": 1,
                "current_phase": "PROPOSING",
                "completed_generations": 0,
                "requested_generations": 2,
                "phase_started_at": recent,
                "last_event": "proposal_started",
                "last_event_at": recent,
                "generations": [],
            }
        ),
        encoding="utf-8",
    )

    research = build_runtime_snapshot(state, managed_run_id=None)["research"]

    assert research["stale_after_seconds"] == 600.0
    assert research["is_stale"] is False
    assert research["consistency_status"] == "OK"


def test_research_snapshot_surfaces_projection_consistency_issues(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "COMPLETED",
                "research_run_id": "research-inconsistent",
                "current_generation": 4,
                "current_phase": "BACKTESTING",
                "completed_generations": 3,
                "requested_generations": 2,
                "phase_started_at": now,
                "last_event": "run_completed",
                "last_event_at": now,
                "generations": [{"generation": 1, "status": "REJECT"}],
            }
        ),
        encoding="utf-8",
    )

    research = build_runtime_snapshot(state, managed_run_id=None)["research"]

    assert research["completion_percent"] == 100.0
    assert research["consistency_status"] == "WARN"
    assert set(research["consistency_issues"]) == {
        "COMPLETED_EXCEEDS_REQUESTED",
        "GENERATION_RECORD_COUNT_MISMATCH",
        "CURRENT_GENERATION_EXCEEDS_REQUESTED",
        "EVENT_PHASE_MISMATCH",
        "TERMINAL_PHASE_MISMATCH",
        "COMPLETED_RUN_GENERATION_MISMATCH",
    }



def test_evaluation_snapshot_reports_retry_and_terminal_queue_state(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    queue = PersistentJobQueue(state)

    queue.enqueue(
        Job("retry-pending", {"managed_run_id": "managed-eval"}, max_attempts=3)
    )
    assert queue.claim(job_id="retry-pending", lease_seconds=30) is not None
    queue.fail("retry-pending", "timeout detail", error_class="TimeoutError")
    queue.retry_terminal("retry-pending")

    queue.enqueue(
        Job("exhausted", {"managed_run_id": "managed-eval"}, max_attempts=1)
    )
    assert queue.claim(job_id="exhausted", lease_seconds=30) is not None
    queue.timeout("exhausted")
    queue.retry_terminal("exhausted")

    queue.enqueue(
        Job("succeeded", {"managed_run_id": "managed-eval"}, max_attempts=2)
    )
    assert queue.claim(job_id="succeeded", lease_seconds=30) is not None
    queue.succeed("succeeded", {"status": "COMPLETED"})

    system = state / "system"
    with (system / "evaluation-jobs.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        for record in (
            {
                "managed_run_id": "managed-eval",
                "job_id": "retry-pending",
                "status": "TIMED_OUT",
                "queue_attempt": 1,
                "max_attempts": 3,
                "error_class": "TimeoutError",
                "execution_mode": "docker_worker",
                "isolated": True,
                "timeout_enforced": True,
                "attempt_id": "retry-attempt",
                "generation": 1,
                "error": "must not leak",
            },
            {
                "managed_run_id": "managed-eval",
                "job_id": "succeeded",
                "status": "SUCCEEDED",
                "queue_attempt": 1,
                "max_attempts": 2,
                "error_class": None,
                "execution_mode": "docker_worker",
                "isolated": True,
                "timeout_enforced": True,
                "attempt_id": "success-attempt",
                "generation": 2,
            },
        ):
            handle.write(json.dumps(record) + "\n")

    evaluation = build_runtime_snapshot(
        state, managed_run_id="managed-eval"
    )["evaluation"]

    assert evaluation["counts"] == {
        "QUEUED": 1,
        "RETRY_EXHAUSTED": 1,
        "SUCCEEDED": 1,
    }
    assert evaluation["total_jobs"] == 3
    assert evaluation["terminal_jobs"] == 2
    assert evaluation["retry_summary"] == {
        "jobs_with_retries": 0,
        "retries_used": 0,
        "retry_pending_jobs": 1,
        "retry_exhausted_jobs": 1,
    }
    assert evaluation["queue_health"] == "WARN"
    assert evaluation["queue_issues"] == ["RETRY_EXHAUSTED_PRESENT"]
    queued = evaluation["queued_jobs"][0]
    assert queued["job_id"] == "retry-pending"
    assert queued["queue_attempt"] == 1
    assert queued["max_attempts"] == 3
    assert queued["attempts_remaining"] == 2
    assert queued["retry_pending"] is True
    assert [job["status"] for job in evaluation["recent_terminal_jobs"]] == [
        "SUCCEEDED",
        "RETRY_EXHAUSTED",
    ]
    assert [attempt["status"] for attempt in evaluation["recent_attempts"]] == [
        "SUCCEEDED",
        "TIMED_OUT",
    ]
    assert evaluation["latest_job"]["status"] == "SUCCEEDED"
    assert "must not leak" not in json.dumps(evaluation)


def test_evaluation_snapshot_marks_expired_running_lease_without_mutation(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("stale", {"managed_run_id": "managed-eval"}, max_attempts=2))
    assert queue.claim(job_id="stale", lease_seconds=30) is not None

    with sqlite3.connect(queue.path) as connection:
        connection.execute(
            "UPDATE jobs SET lease_until=? WHERE job_id=?",
            ("2020-01-01T00:00:00+00:00", "stale"),
        )
        connection.commit()

    before = queue.get("stale")
    evaluation = build_runtime_snapshot(
        state, managed_run_id="managed-eval"
    )["evaluation"]
    after = queue.get("stale")

    assert evaluation["queue_health"] == "WARN"
    assert "EXPIRED_RUNNING_LEASE" in evaluation["queue_issues"]
    assert evaluation["active_jobs"][0]["lease_expired"] is True
    assert before.status == after.status
    assert before.attempt == after.attempt
    assert after.status.value == "RUNNING"


def test_evaluation_snapshot_reports_unreadable_queue_without_repairing_it(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    queue_path = state / "system" / "evaluation-jobs" / "queue.sqlite"
    queue_path.parent.mkdir(parents=True)
    original = b"not-a-sqlite-database"
    queue_path.write_bytes(original)

    evaluation = build_runtime_snapshot(state, managed_run_id="managed-eval")[
        "evaluation"
    ]

    assert evaluation["status"] == "UNAVAILABLE"
    assert evaluation["queue_health"] == "UNAVAILABLE"
    assert evaluation["queue_issues"] == ["QUEUE_UNREADABLE"]
    assert queue_path.read_bytes() == original


def test_evaluation_attempt_history_filters_managed_run_and_is_bounded(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    records = []
    for index in range(25):
        records.append(
            {
                "managed_run_id": "managed-a",
                "job_id": f"job-{index}",
                "status": "SUCCEEDED",
                "queue_attempt": 1,
                "max_attempts": 2,
                "execution_mode": "local_scheduler",
                "isolated": False,
                "timeout_enforced": False,
            }
        )
    records.append(
        {
            "managed_run_id": "managed-b",
            "job_id": "foreign-job",
            "status": "FAILED",
            "queue_attempt": 1,
            "max_attempts": 1,
            "error_class": "ValueError",
        }
    )
    (system / "evaluation-jobs.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )

    evaluation = build_runtime_snapshot(state, managed_run_id="managed-a")[
        "evaluation"
    ]

    assert len(evaluation["recent_attempts"]) == 20
    assert evaluation["recent_attempts"][0]["job_id"] == "job-24"
    assert evaluation["recent_attempts"][-1]["job_id"] == "job-5"
    assert evaluation["latest_job"]["job_id"] == "job-24"
    assert all(
        attempt["job_id"] != "foreign-job"
        for attempt in evaluation["recent_attempts"]
    )



def test_evidence_and_knowledge_snapshot_reports_verified_projection_sync(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "COMPLETED",
                "research_run_id": "research-evidence",
                "current_generation": 1,
                "current_phase": "COMPLETED",
                "completed_generations": 1,
                "requested_generations": 1,
                "last_event": "run_completed",
                "last_event_at": datetime.now(timezone.utc).isoformat(),
                "generations": [{"generation": 1, "status": "SURVIVOR"}],
            }
        ),
        encoding="utf-8",
    )
    store = EvidenceStore(state)
    store.append(
        "run",
        "run:research-evidence",
        {
            "research_run_id": "research-evidence",
            "requested_generations": 1,
            "seed": 0,
        },
    )
    store.append(
        "manifest",
        "manifest:research-evidence",
        {
            "research_run_id": "research-evidence",
            "comparison_key": "comparison-a",
        },
    )
    store.append(
        "attempt",
        "attempt:attempt-a",
        {
            "research_run_id": "research-evidence",
            "attempt_id": "attempt-a",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "candidate-a",
                    "family": "trend",
                    "status": "SURVIVOR",
                    "failed_gates": [],
                }
            ],
        },
    )
    store.append(
        "generation",
        "generation:research-evidence:1",
        {
            "research_run_id": "research-evidence",
            "generation": 1,
            "status": "SURVIVOR",
            "attempt_id": "attempt-a",
        },
    )
    store.append(
        "end",
        "end:research-evidence",
        {
            "research_run_id": "research-evidence",
            "status": "COMPLETED",
        },
    )
    sync_knowledge(state)

    snapshot = build_runtime_snapshot(state, managed_run_id=None)
    evidence = snapshot["evidence"]
    knowledge = snapshot["knowledge"]

    assert evidence["integrity_status"] == "VERIFIED"
    assert evidence["link_status"] == "LINKED"
    assert evidence["manifest_present"] is True
    assert evidence["attempt_count"] == 1
    assert evidence["generation_count"] == 1
    assert evidence["last_event_id"] == "end:research-evidence"
    assert evidence["last_attempt_id"] == "attempt-a"
    assert evidence["last_attempt_status"] == "COMPLETED"
    assert evidence["last_generation"] == 1
    assert evidence["last_generation_status"] == "SURVIVOR"
    assert evidence["terminal_status"] == "COMPLETED"

    assert knowledge["status"] == "CONNECTED"
    assert knowledge["sync_status"] == "IN_SYNC"
    assert knowledge["evidence_experiment_count"] == 1
    assert knowledge["projected_experiment_count"] == 1
    assert knowledge["missing_experiment_count"] == 0
    assert knowledge["projection_coverage_percent"] == 100.0


def test_knowledge_snapshot_detects_stale_projection_without_syncing_it(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    store = EvidenceStore(state)
    store.append(
        "run",
        "run:research-stale-knowledge",
        {
            "research_run_id": "research-stale-knowledge",
            "requested_generations": 1,
            "seed": 0,
        },
    )
    store.append(
        "attempt",
        "attempt:stale-a",
        {
            "research_run_id": "research-stale-knowledge",
            "attempt_id": "stale-a",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "candidate-stale",
                    "family": "trend",
                    "status": "REJECT",
                    "failed_gates": ["robustness"],
                }
            ],
        },
    )
    knowledge_path = state / "knowledge.json"
    stale = {
        "schema_version": 1,
        "known_good": [],
        "known_bad": [],
        "unexplored": [],
        "interactions": [],
    }
    knowledge_path.write_text(json.dumps(stale), encoding="utf-8")
    before = knowledge_path.read_bytes()

    knowledge = build_runtime_snapshot(state, managed_run_id=None)["knowledge"]

    assert knowledge["status"] == "CONNECTED"
    assert knowledge["sync_status"] == "STALE"
    assert knowledge["evidence_experiment_count"] == 1
    assert knowledge["projected_experiment_count"] == 0
    assert knowledge["missing_experiment_count"] == 1
    assert knowledge["projection_coverage_percent"] == 0.0
    assert knowledge_path.read_bytes() == before


def test_champion_snapshot_links_candidate_to_evidence_and_audit(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    store = EvidenceStore(state)
    store.append(
        "run",
        "run:champion-run",
        {
            "research_run_id": "champion-run",
            "requested_generations": 1,
            "seed": 0,
        },
    )
    store.append(
        "attempt",
        "attempt:champion-attempt",
        {
            "research_run_id": "champion-run",
            "attempt_id": "champion-attempt",
            "generation": 4,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "champion-candidate",
                    "family": "trend",
                    "status": "SURVIVOR",
                    "score": 1.25,
                    "failed_gates": [],
                }
            ],
        },
    )
    (state / "champion.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "CHAMPION",
                "champion": {
                    "status": "CHAMPION",
                    "champion_hash": "champion-candidate",
                    "family": "trend",
                    "score": 1.25,
                },
            }
        ),
        encoding="utf-8",
    )
    (state / "audit.jsonl").write_text(
        json.dumps(
            {
                "event": "promote_champion",
                "actor": "human",
                "timestamp": "2026-09-27T01:02:03+00:00",
                "input_hash": "opaque",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    strategy = build_runtime_snapshot(state, managed_run_id=None)["strategy_state"]

    assert strategy["champion_status"] == "CHAMPION"
    assert strategy["champion_hash"] == "champion-candidate"
    assert strategy["champion_family"] == "trend"
    assert strategy["champion_generation"] == 4
    assert strategy["champion_evidence_status"] == "LINKED"
    assert strategy["champion_research_run_id"] == "champion-run"
    assert strategy["champion_attempt_id"] == "champion-attempt"
    assert strategy["champion_candidate_status"] == "SURVIVOR"
    assert strategy["promotion_audit_status"] == "PRESENT"
    assert strategy["promotion_audit_records"] == 1
    assert strategy["last_promotion_at"] == "2026-09-27T01:02:03+00:00"
    assert strategy["frontier_status"] == "NOT_CONNECTED"
    assert strategy["rescue_status"] == "NOT_CONNECTED"


def test_champion_snapshot_does_not_invent_evidence_provenance(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "champion.json").write_text(
        json.dumps(
            {
                "status": "CHAMPION",
                "champion": {
                    "status": "CHAMPION",
                    "champion_hash": "unknown-candidate",
                    "score": 9.0,
                },
            }
        ),
        encoding="utf-8",
    )

    strategy = build_runtime_snapshot(state, managed_run_id=None)["strategy_state"]

    assert strategy["champion_evidence_status"] == "NOT_FOUND"
    assert strategy["champion_research_run_id"] is None
    assert strategy["champion_attempt_id"] is None
    assert strategy["promotion_audit_status"] == "MISSING"


def test_evidence_integrity_error_propagates_to_derived_observability(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    store = EvidenceStore(state)
    store.append(
        "run",
        "run:broken",
        {
            "research_run_id": "broken",
            "requested_generations": 1,
            "seed": 0,
        },
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER prevent_update")
        connection.execute("UPDATE events SET checksum='broken' WHERE id='run:broken'")
        connection.commit()
    system = state / "system"
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "broken",
                "current_generation": 1,
                "current_phase": "GENERATION",
                "completed_generations": 0,
                "requested_generations": 1,
            }
        ),
        encoding="utf-8",
    )
    (state / "champion.json").write_text(
        json.dumps(
            {
                "status": "CHAMPION",
                "champion": {
                    "status": "CHAMPION",
                    "champion_hash": "candidate-broken",
                },
            }
        ),
        encoding="utf-8",
    )

    snapshot = build_runtime_snapshot(state, managed_run_id=None)

    assert snapshot["evidence"]["integrity_status"] == "INTEGRITY_ERROR"
    assert snapshot["evidence"]["link_status"] == "INTEGRITY_ERROR"
    assert snapshot["knowledge"]["sync_status"] == "EVIDENCE_INTEGRITY_ERROR"
    assert (
        snapshot["strategy_state"]["champion_evidence_status"]
        == "EVIDENCE_INTEGRITY_ERROR"
    )



def test_runtime_health_is_healthy_when_no_active_fault_exists(tmp_path: Path) -> None:
    state = tmp_path / "state"

    snapshot = build_runtime_snapshot(state, managed_run_id=None)

    assert snapshot["health"] == {
        "status": "HEALTHY",
        "primary_source": None,
        "primary_code": None,
        "issue_count": 0,
        "issues": [],
        "recovery_action_count": 0,
        "last_recovery_event": None,
        "interrupted_research_run_id": None,
    }
    assert not state.exists()


def test_runtime_health_prioritizes_evidence_integrity_over_interruption(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "INTERRUPTED",
                "research_run_id": "broken-run",
                "current_generation": 1,
                "current_phase": "INTERRUPTED",
                "completed_generations": 0,
                "requested_generations": 1,
                "last_event": "run_interrupted",
                "last_event_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    store = EvidenceStore(state)
    store.append(
        "run",
        "run:broken-run",
        {
            "research_run_id": "broken-run",
            "requested_generations": 1,
            "seed": 0,
        },
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER prevent_update")
        connection.execute(
            "UPDATE events SET checksum='broken' WHERE id='run:broken-run'"
        )
        connection.commit()

    health = build_runtime_snapshot(
        state,
        managed_run_id="managed-broken",
        recovery_state={
            "interrupted_research_run_id": "broken-run",
            "evidence_closed": False,
        },
    )["health"]

    assert health["status"] == "FAILING"
    assert health["primary_source"] == "evidence"
    assert health["primary_code"] == "EVIDENCE_INTEGRITY_ERROR"
    assert any(issue["code"] == "RESEARCH_INTERRUPTED" for issue in health["issues"])
    assert health["interrupted_research_run_id"] == "broken-run"


def test_runtime_health_reports_interrupted_research_as_distinct_state(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "INTERRUPTED",
                "research_run_id": "interrupted-run",
                "current_generation": 2,
                "current_phase": "INTERRUPTED",
                "completed_generations": 1,
                "requested_generations": 3,
                "last_event": "run_interrupted",
                "last_event_at": datetime.now(timezone.utc).isoformat(),
                "generations": [{"generation": 1, "status": "REJECT"}],
            }
        ),
        encoding="utf-8",
    )

    health = build_runtime_snapshot(
        state,
        managed_run_id="managed-interrupted",
        recovery_state={
            "interrupted_research_run_id": "interrupted-run",
            "cancelled_orphaned_jobs": ["job-a"],
            "reconciled_jobs": ["job-a", "job-b"],
            "evidence_closed": True,
        },
    )["health"]

    assert health["status"] == "INTERRUPTED"
    assert health["primary_code"] == "RESEARCH_INTERRUPTED"
    assert health["recovery_action_count"] == 2
    assert health["interrupted_research_run_id"] == "interrupted-run"


def test_runtime_health_prioritizes_unavailable_queue_over_stale_research(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    old = (datetime.now(timezone.utc) - timedelta(seconds=1900)).isoformat()
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "stale-run",
                "current_generation": 1,
                "current_phase": "BACKTESTING",
                "completed_generations": 0,
                "requested_generations": 1,
                "phase_started_at": old,
                "last_event": "evaluation_started",
                "last_event_at": old,
            }
        ),
        encoding="utf-8",
    )
    queue_path = system / "evaluation-jobs" / "queue.sqlite"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_bytes(b"not sqlite")

    health = build_runtime_snapshot(state, managed_run_id="managed-stale")["health"]

    assert health["status"] == "UNAVAILABLE"
    assert health["primary_source"] == "evaluation"
    assert health["primary_code"] == "EVALUATION_QUEUE_UNAVAILABLE"
    assert any(issue["code"] == "RESEARCH_STALE" for issue in health["issues"])


def test_runtime_health_reports_stale_without_converting_it_to_failure(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    system = state / "system"
    system.mkdir(parents=True)
    old = (datetime.now(timezone.utc) - timedelta(seconds=1900)).isoformat()
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": "stale-only",
                "current_generation": 1,
                "current_phase": "BACKTESTING",
                "completed_generations": 0,
                "requested_generations": 1,
                "phase_started_at": old,
                "last_event": "evaluation_started",
                "last_event_at": old,
            }
        ),
        encoding="utf-8",
    )

    health = build_runtime_snapshot(state, managed_run_id=None)["health"]

    assert health["status"] == "STALE"
    assert health["primary_source"] == "research"
    assert health["primary_code"] == "RESEARCH_STALE"


def test_runtime_health_aggregates_degraded_sources_without_raw_details(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    (state / "knowledge.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "known_good": [],
                "known_bad": [],
                "unexplored": [],
                "interactions": [],
            }
        ),
        encoding="utf-8",
    )
    (state / "champion.json").write_text(
        json.dumps(
            {
                "status": "CHAMPION",
                "champion": {
                    "status": "CHAMPION",
                    "champion_hash": "unlinked-champion",
                    "score": 1.0,
                },
            }
        ),
        encoding="utf-8",
    )
    llm = state / "llm"
    llm.mkdir()
    (llm / "status.json").write_text(
        json.dumps(
            {
                "provider": "codex_exec",
                "status": "OFFLINE",
                "last_result": "TimeoutError: secret provider detail",
                "operation": "propose",
            }
        ),
        encoding="utf-8",
    )
    heartbeat = state / "worker-heartbeats"
    heartbeat.mkdir()
    (heartbeat / "worker-a.json").write_text(
        json.dumps(
            {
                "worker_id": "worker-a",
                "role": "evaluation",
                "status": "FAILED",
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "error": "ValueError: secret worker detail",
            }
        ),
        encoding="utf-8",
    )

    snapshot = build_runtime_snapshot(state, managed_run_id=None)
    health = snapshot["health"]

    assert health["status"] == "DEGRADED"
    codes = {issue["code"] for issue in health["issues"]}
    assert "LLM_PROVIDER_UNAVAILABLE" in codes
    assert "WORKER_FAILED" in codes
    assert "CHAMPION_EVIDENCE_NOT_FOUND" in codes
    assert "PROMOTION_AUDIT_MISSING" in codes
    serialized = json.dumps(health)
    assert "secret provider detail" not in serialized
    assert "secret worker detail" not in serialized
    assert any(
        issue["error_class"] == "TimeoutError"
        for issue in health["issues"]
        if issue["source"] == "llm"
    )
    assert any(
        issue["error_class"] == "ValueError"
        for issue in health["issues"]
        if issue["source"] == "worker:worker-a"
    )
