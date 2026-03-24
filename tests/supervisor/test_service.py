from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
import threading

import pytest

from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.supervisor.process_lock import (
    ProcessLock,
    ProcessLockTimeoutError,
)
from finance_autoresearch.supervisor.service import SupervisorService


@dataclass(slots=True)
class StubSeedValidator:
    valid: bool = True
    message: str = "seed baseline validated"
    calls: list[str | None] = field(init=False, default_factory=list)

    def __call__(self, project_id: str | None) -> tuple[bool, str]:
        self.calls.append(project_id)
        return self.valid, self.message


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStateStore:
    repository = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    yield repository
    repository.close()


@pytest.fixture
def seed_validator() -> StubSeedValidator:
    return StubSeedValidator()


@pytest.fixture
def supervisor(
    store: SQLiteStateStore,
    seed_validator: StubSeedValidator,
) -> SupervisorService:
    return SupervisorService(
        state_store=store,
        seed_validator=seed_validator,
        run_id_factory=lambda: "run-001",
    )


def make_command(command: str, **overrides: object) -> dict[str, object]:
    normalized = {
        "command": command,
        "project_id": "finance",
        "source": "cli",
        "requested_by": "tester",
        "requested_at": "2026-03-25T00:00:00+00:00",
        "payload": {},
    }
    normalized.update(overrides)
    return normalized


def test_start_pipeline_allowed_from_idle(supervisor: SupervisorService) -> None:
    response = supervisor.handle(make_command("start_pipeline"))

    assert response == {
        "accepted": True,
        "project_state": "active",
        "pipeline_state": "running",
        "autoresearch_state": "idle",
        "pending_command": None,
        "message": "pipeline started",
        "run_id": None,
    }


def test_start_pipeline_allowed_from_degraded(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    store.set_status(
        project_state="degraded",
        pipeline_state="failed",
        autoresearch_state="failed",
    )

    response = supervisor.handle(make_command("start_pipeline"))

    assert response["accepted"] is True
    assert response["project_state"] == "active"
    assert response["pipeline_state"] == "running"


def test_start_autoresearch_rejects_without_successful_pipeline(
    supervisor: SupervisorService,
) -> None:
    response = supervisor.handle(make_command("start_autoresearch"))

    assert response["accepted"] is False
    assert response["project_state"] == "idle"
    assert response["pipeline_state"] == "idle"
    assert response["autoresearch_state"] == "idle"
    assert response["run_id"] is None


def test_start_autoresearch_sets_active_running_and_returns_run_id(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
    seed_validator: StubSeedValidator,
) -> None:
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )

    response = supervisor.handle(
        make_command("start_autoresearch", source="dashboard", payload={"reason": "manual"})
    )
    persisted_state = store.get_status()

    assert response["accepted"] is True
    assert response["project_state"] == "active"
    assert response["autoresearch_state"] == "running"
    assert response["run_id"] == "run-001"
    assert persisted_state.active_run_id == "run-001"
    assert seed_validator.calls == ["finance"]


def test_start_autoresearch_does_not_auto_run_pipeline(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )

    response = supervisor.handle(make_command("start_autoresearch"))

    assert response["accepted"] is True
    assert response["pipeline_state"] == "success"


def test_duplicate_start_autoresearch_is_rejected(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )
    first_response = supervisor.handle(make_command("start_autoresearch"))

    duplicate_response = supervisor.handle(make_command("start_autoresearch"))

    assert first_response["accepted"] is True
    assert duplicate_response["accepted"] is False
    assert duplicate_response["run_id"] == "run-001"


def test_pause_and_resume_autoresearch_transitions(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )
    supervisor.handle(make_command("start_autoresearch"))

    paused = supervisor.handle(make_command("pause_autoresearch"))
    resumed = supervisor.handle(make_command("resume_autoresearch"))

    assert paused["accepted"] is True
    assert paused["project_state"] == "paused"
    assert paused["autoresearch_state"] == "paused"
    assert resumed["accepted"] is True
    assert resumed["project_state"] == "active"
    assert resumed["autoresearch_state"] == "running"


def test_stop_while_running_sets_pending_command_only(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )
    supervisor.handle(make_command("start_autoresearch"))

    response = supervisor.handle(make_command("stop_autoresearch"))
    persisted_state = store.get_status()

    assert response["accepted"] is True
    assert response["project_state"] == "active"
    assert response["autoresearch_state"] == "running"
    assert response["pending_command"] == "stop_autoresearch"
    assert response["run_id"] == "run-001"
    assert persisted_state.active_run_id == "run-001"
    assert persisted_state.pending_command == "stop_autoresearch"


def test_stop_while_paused_transitions_to_success_idle_and_clears_active_run(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )
    supervisor.handle(make_command("start_autoresearch"))
    supervisor.handle(make_command("pause_autoresearch"))

    response = supervisor.handle(make_command("stop_autoresearch"))
    persisted_state = store.get_status()

    assert response["accepted"] is True
    assert response["project_state"] == "idle"
    assert response["autoresearch_state"] == "success"
    assert response["pending_command"] is None
    assert response["run_id"] is None
    assert persisted_state.active_run_id is None
    assert persisted_state.pending_command is None


@pytest.mark.parametrize("project_state", ["idle", "degraded"])
def test_reset_project_allowed_only_from_idle_or_degraded(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
    project_state: str,
) -> None:
    heartbeat = datetime(2026, 3, 25, 0, 30, tzinfo=timezone.utc)
    store.set_status(
        project_state=project_state,
        pipeline_state="success" if project_state == "idle" else "failed",
        autoresearch_state="success" if project_state == "idle" else "failed",
    )
    store.set_active_run("run-001")
    store.set_current_stage("analyze_candidate")
    store.set_pending_command("stop_autoresearch")
    store.record_heartbeat("pipeline", heartbeat)
    store.record_heartbeat("autoresearch", heartbeat)
    store.set_candidate_revision("candidate-001")
    store.set_baseline_revision("baseline-001")
    store.set_recovery_marker("iteration-001")

    response = supervisor.handle(make_command("reset_project"))
    persisted_state = store.get_status()

    assert response["accepted"] is True
    assert response["project_state"] == "idle"
    assert response["pipeline_state"] == "idle"
    assert response["autoresearch_state"] == "idle"
    assert response["run_id"] is None
    assert persisted_state.active_run_id is None
    assert persisted_state.current_stage is None
    assert persisted_state.pending_command is None
    assert persisted_state.pipeline_heartbeat_at is None
    assert persisted_state.autoresearch_heartbeat_at is None
    assert persisted_state.candidate_revision is None
    assert persisted_state.baseline_revision == "baseline-001"
    assert persisted_state.recovery_marker is None


def test_reset_project_rejects_when_active(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    store.set_status(
        project_state="active",
        pipeline_state="running",
        autoresearch_state="running",
    )
    store.set_active_run("run-001")

    response = supervisor.handle(make_command("reset_project"))

    assert response["accepted"] is False
    assert response["project_state"] == "active"
    assert response["pipeline_state"] == "running"
    assert response["autoresearch_state"] == "running"
    assert response["run_id"] == "run-001"


def test_invalid_command_shape_is_rejected_without_persisting_history(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    response = supervisor.handle(
        {
            "command": "launch",
            "project_id": "finance",
            "source": "cli",
            "requested_by": "tester",
            "requested_at": "not-an-iso-timestamp",
            "payload": [],
        }
    )

    assert response["accepted"] is False
    assert response["message"].startswith("invalid command")
    assert store.list_commands() == []


def test_invalid_seed_baseline_rejects_and_degrades_project(
    store: SQLiteStateStore,
    seed_validator: StubSeedValidator,
) -> None:
    seed_validator.valid = False
    seed_validator.message = "baseline guardrails failed"
    supervisor = SupervisorService(
        state_store=store,
        seed_validator=seed_validator,
        run_id_factory=lambda: "run-001",
    )
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )

    response = supervisor.handle(make_command("start_autoresearch"))
    persisted_state = store.get_status()

    assert response["accepted"] is False
    assert response["project_state"] == "degraded"
    assert response["pipeline_state"] == "success"
    assert response["autoresearch_state"] == "failed"
    assert response["run_id"] is None
    assert response["message"] == "baseline guardrails failed"
    assert persisted_state.project_state == "degraded"
    assert persisted_state.autoresearch_state == "failed"


def test_start_autoresearch_rejects_when_seed_validator_is_missing(
    store: SQLiteStateStore,
) -> None:
    supervisor = SupervisorService(
        state_store=store,
        run_id_factory=lambda: "run-001",
    )
    store.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )

    response = supervisor.handle(make_command("start_autoresearch"))
    persisted_state = store.get_status()

    assert response["accepted"] is False
    assert response["message"] == "seed validator is not configured"
    assert response["project_state"] == "degraded"
    assert response["autoresearch_state"] == "failed"
    assert persisted_state.project_state == "degraded"
    assert persisted_state.autoresearch_state == "failed"


def test_start_autoresearch_does_not_call_seed_validator_when_pipeline_is_not_ready(
    store: SQLiteStateStore,
    seed_validator: StubSeedValidator,
) -> None:
    supervisor = SupervisorService(
        state_store=store,
        seed_validator=seed_validator,
        run_id_factory=lambda: "run-001",
    )

    response = supervisor.handle(make_command("start_autoresearch"))

    assert response["accepted"] is False
    assert seed_validator.calls == []


def test_mapping_input_is_accepted_as_a_valid_command(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    command = MappingProxyType(make_command("start_pipeline"))

    response = supervisor.handle(command)
    persisted_command = store.list_commands(limit=1)[0]

    assert response["accepted"] is True
    assert persisted_command.command == "start_pipeline"


def test_concurrent_start_autoresearch_is_serialized_across_services(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state.db"
    bootstrap = SQLiteStateStore(db_path=db_path, project_id="finance")
    bootstrap.set_status(
        project_state="idle",
        pipeline_state="success",
        autoresearch_state="idle",
    )
    bootstrap.close()

    barrier = threading.Barrier(2)

    def start(run_id: str) -> dict[str, object]:
        store = SQLiteStateStore(db_path=db_path, project_id="finance")
        service = SupervisorService(
            state_store=store,
            seed_validator=StubSeedValidator(),
            run_id_factory=lambda: run_id,
        )
        barrier.wait()
        try:
            return service.handle(make_command("start_autoresearch"))
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(start, "run-a")
        future_b = executor.submit(start, "run-b")
        results = [future_a.result(), future_b.result()]

    accepted = [result for result in results if result["accepted"] is True]
    rejected = [result for result in results if result["accepted"] is False]

    final_store = SQLiteStateStore(db_path=db_path, project_id="finance")
    try:
        final_state = final_store.get_status()
    finally:
        final_store.close()

    assert len(accepted) == 1
    assert accepted[0]["run_id"] in {"run-a", "run-b"}
    assert len(rejected) == 1
    assert rejected[0]["run_id"] == accepted[0]["run_id"]
    assert final_state.active_run_id == accepted[0]["run_id"]


def test_process_lock_reclaims_stale_lock_file(tmp_path: Path) -> None:
    lock_path = tmp_path / "supervisor.lock"
    lock_path.write_text('{"pid": 0, "acquired_at": "2026-03-25T00:00:00+00:00"}')

    with ProcessLock(lock_path=lock_path, timeout_seconds=0.1, poll_interval_seconds=0.01):
        assert lock_path.exists()

    assert lock_path.exists() is False


def test_process_lock_times_out_on_unreadable_lock_file(tmp_path: Path) -> None:
    lock_path = tmp_path / "supervisor.lock"
    lock_path.write_text("")

    with pytest.raises(ProcessLockTimeoutError):
        with ProcessLock(
            lock_path=lock_path,
            timeout_seconds=0.05,
            poll_interval_seconds=0.01,
        ):
            pass


def test_normalized_command_history_is_persisted_for_handled_commands(
    store: SQLiteStateStore,
    supervisor: SupervisorService,
) -> None:
    response = supervisor.handle(
        make_command(
            "start_pipeline",
            source="telegram_control",
            requested_by="ops-user",
            payload={"force_refresh": True},
        )
    )
    commands = store.list_commands(limit=1)

    assert response["accepted"] is True
    assert len(commands) == 1
    assert commands[0].command == "start_pipeline"
    assert commands[0].source == "telegram_control"
    assert commands[0].requested_by == "ops-user"
    assert commands[0].payload == {"force_refresh": True}
    assert commands[0].accepted is True
    assert commands[0].project_state == "active"
    assert commands[0].pipeline_state == "running"
    assert commands[0].autoresearch_state == "idle"
    assert commands[0].pending_command is None
    assert commands[0].message == "pipeline started"
    assert commands[0].run_id is None
