from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
