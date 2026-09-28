from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import runtime.system_controller as controller_module
from memory.evidence_store import EvidenceStore
from runtime.docker_evaluation import docker_evaluation_container_name
from runtime.persistent_queue import PersistentJobQueue
from runtime.queue import Job, JobStatus
from runtime.system_controller import PreflightReport, SystemController, SystemLaunchConfig


def test_preflight_local_mode_does_not_require_docker(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("QUANT_EVALUATION_EXECUTION", raising=False)
    monkeypatch.setattr(controller_module.shutil, "which", lambda name: None)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "mode.json").write_text(
        '{"selected_mode":"paper","orders_enabled":false}', encoding="utf-8"
    )
    controller = SystemController(state_dir=state_dir, project_root=tmp_path)
    config = SystemLaunchConfig(
        source_path="strategies/missing.py",
        data_path="data/missing.parquet",
    )

    report = controller.preflight(config)

    assert report.status == "BLOCKED"
    issue_ids = {issue.id for issue in report.issues}
    assert {"strategy_source", "market_data", "codex_cli"}.issubset(issue_ids)
    assert "docker_cli" not in issue_ids
    docker_check = next(check for check in report.checks if check["id"] == "docker_cli")
    assert docker_check["status"] == "PASS"
    assert "선택 사항" in docker_check["label"]


def test_preflight_docker_mode_requires_docker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUANT_EVALUATION_EXECUTION", "docker_worker")
    monkeypatch.setattr(controller_module.shutil, "which", lambda name: None)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "mode.json").write_text(
        '{"selected_mode":"paper","orders_enabled":false}', encoding="utf-8"
    )
    controller = SystemController(state_dir=state_dir, project_root=tmp_path)

    report = controller.preflight(
        SystemLaunchConfig(
            source_path="strategies/missing.py",
            data_path="data/missing.parquet",
        )
    )

    issue_ids = {issue.id for issue in report.issues}
    assert "docker_cli" in issue_ids


def test_preflight_rejects_unknown_evaluation_backend(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("QUANT_EVALUATION_EXECUTION", "unknown")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "mode.json").write_text(
        '{"selected_mode":"paper","orders_enabled":false}', encoding="utf-8"
    )
    controller = SystemController(state_dir=state_dir, project_root=tmp_path)

    report = controller.preflight(
        SystemLaunchConfig(
            source_path="strategies/missing.py",
            data_path="data/missing.parquet",
        )
    )

    assert "evaluation_execution" in {issue.id for issue in report.issues}


def test_system_launch_defaults_match_research_policy() -> None:
    config = SystemLaunchConfig(source_path="strategy.json", data_path="data.parquet")

    assert config.min_qqq_cagr_delta == 0.10
    assert config.min_annual_trades == 30


def test_start_does_not_spawn_processes_when_preflight_is_blocked(tmp_path: Path) -> None:
    controller = SystemController(state_dir=tmp_path / "state", project_root=tmp_path)
    spawned: list[list[str]] = []
    controller._process_factory = lambda command, cwd: spawned.append(command)  # type: ignore[assignment]

    result = controller.start(
        SystemLaunchConfig(source_path="missing.py", data_path="missing.parquet")
    )

    assert result["status"] == "BLOCKED"
    assert spawned == []


def test_start_launches_dashboard_and_canonical_research_worker_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("QUANT_EVALUATION_EXECUTION", raising=False)
    controller = SystemController(state_dir=tmp_path / "state", project_root=tmp_path)
    (tmp_path / "strategy.py").write_text("strategy", encoding="utf-8")
    (tmp_path / "data.parquet").write_bytes(b"fixture")
    controller.preflight = lambda config: PreflightReport("READY", (), ())  # type: ignore[method-assign]
    spawned: list[list[str]] = []

    class FakeProcess:
        pid = 100

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

    def factory(command: list[str], cwd: Path) -> FakeProcess:
        spawned.append(command)
        return FakeProcess()

    controller._process_factory = factory  # type: ignore[assignment]
    result = controller.start(
        SystemLaunchConfig(
            source_path="strategy.py",
            data_path="data.parquet",
            method="random",
            count=9,
            seed=4,
            repeat_generations=3,
            interval_seconds=2,
        )
    )

    assert result["status"] == "STARTED"
    assert result["container_name"] is None
    assert result["evaluation_execution"] == "local_scheduler"
    assert {item["id"] for item in result["components"]} == {
        "dashboard",
        "research_worker",
        "evaluation_backend",
    }
    assert len(spawned) == 2
    assert all(command[0] != "docker" for command in spawned)
    research = next(command for command in spawned if "runtime.system_worker" in command)
    assert research[research.index("--role") + 1] == "research"
    assert research[research.index("--data-path") + 1] == "data.parquet"
    assert research[research.index("--method") + 1] == "random"
    assert research[research.index("--count") + 1] == "9"
    assert research[research.index("--seed") + 1] == "4"
    assert research[research.index("--repeat-generations") + 1] == "3"
    assert research[research.index("--interval-seconds") + 1] == "2"
    assert research[research.index("--evaluation-execution") + 1] == "local_scheduler"




def test_existing_env_file_can_select_docker_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("QUANT_EVALUATION_EXECUTION", raising=False)
    (tmp_path / ".env").write_text(
        "QUANT_EVALUATION_EXECUTION=docker_worker\n",
        encoding="utf-8",
    )
    controller = SystemController(state_dir=tmp_path / "state", project_root=tmp_path)
    (tmp_path / "strategy.py").write_text("strategy", encoding="utf-8")
    (tmp_path / "data.parquet").write_bytes(b"fixture")
    controller.preflight = lambda config: PreflightReport("READY", (), ())  # type: ignore[method-assign]
    spawned: list[list[str]] = []

    class FakeProcess:
        pid = 100

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

    controller._process_factory = lambda command, cwd: (  # type: ignore[assignment]
        spawned.append(command) or FakeProcess()
    )

    result = controller.start(
        SystemLaunchConfig(
            source_path="strategy.py",
            data_path="data.parquet",
            env_file=".env",
        )
    )

    assert result["evaluation_execution"] == "docker_worker"
    research = next(command for command in spawned if "runtime.system_worker" in command)
    assert research[research.index("--evaluation-execution") + 1] == "docker_worker"


def test_start_docker_mode_configures_research_worker_without_standalone_container(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("QUANT_EVALUATION_EXECUTION", "docker_worker")
    controller = SystemController(state_dir=tmp_path / "state", project_root=tmp_path)
    (tmp_path / "strategy.py").write_text("strategy", encoding="utf-8")
    (tmp_path / "data.parquet").write_bytes(b"fixture")
    controller.preflight = lambda config: PreflightReport("READY", (), ())  # type: ignore[method-assign]
    spawned: list[list[str]] = []

    class FakeProcess:
        pid = 100

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

    controller._process_factory = lambda command, cwd: (  # type: ignore[assignment]
        spawned.append(command) or FakeProcess()
    )
    result = controller.start(
        SystemLaunchConfig(
            source_path="strategy.py",
            data_path="data.parquet",
            docker_image="quant-worker:test",
        )
    )

    assert result["evaluation_execution"] == "docker_worker"
    assert len(spawned) == 2
    assert all(command[0] != "docker" for command in spawned)
    research = next(command for command in spawned if "runtime.system_worker" in command)
    assert research[research.index("--evaluation-execution") + 1] == "docker_worker"
    assert research[research.index("--evaluation-docker-image") + 1] == "quant-worker:test"


def test_status_reports_shared_evaluation_backend_activity(tmp_path: Path) -> None:
    state = tmp_path / "state"
    controller = SystemController(state_dir=state, project_root=tmp_path)
    controller._write_state(
        {
            "status": "STARTED",
            "evaluation_execution": "docker_worker",
            "components": [
                {"id": "research_worker", "status": "STARTED"},
                {
                    "id": "evaluation_backend",
                    "status": "CONFIGURED",
                    "mode": "docker_worker",
                },
            ],
        }
    )
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("job-1", {}, max_attempts=2))
    assert queue.claim(job_id="job-1", lease_seconds=30) is not None

    payload = controller.status()

    components = {
        item["id"]: item
        for item in payload["components"]
        if isinstance(item, dict)
    }
    assert components["evaluation_backend"]["status"] == "RUNNING"
    assert components["evaluation_backend"]["active_jobs"] == 1


def test_stop_forcibly_removes_running_docker_jobs_and_cancels_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = tmp_path / "state"
    controller = SystemController(state_dir=state, project_root=tmp_path)
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("evaluation-attempt-1", {}, max_attempts=2))
    claimed = queue.claim(job_id="evaluation-attempt-1", lease_seconds=30)
    assert claimed is not None
    commands: list[list[str]] = []
    monkeypatch.setattr(
        controller_module.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    controller._command_runner = lambda command, cwd: (  # type: ignore[assignment]
        commands.append(command) or (0, "")
    )

    result = controller.stop()

    assert result == {"status": "STOPPED", "components": []}
    expected_name = docker_evaluation_container_name(
        "evaluation-attempt-1", claimed.attempt
    )
    assert ["docker", "rm", "-f", expected_name] in commands
    assert queue.get("evaluation-attempt-1").status is JobStatus.CANCELLED


def test_stop_reports_cleanup_failure_without_claiming_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = tmp_path / "state"
    controller = SystemController(state_dir=state, project_root=tmp_path)
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("job-1", {}, max_attempts=1))
    assert queue.claim(job_id="job-1", lease_seconds=30) is not None
    monkeypatch.setattr(
        controller_module.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    controller._command_runner = lambda command, cwd: (1, "failed")  # type: ignore[assignment]

    result = controller.stop()

    assert result["status"] == "STOP_FAILED"
    assert result["cleanup_failed"] == ["job-1"]
    assert queue.get("job-1").status is JobStatus.RUNNING



def _managed_state(
    controller: SystemController,
    *,
    managed_run_id: str = "run-1",
    dashboard_pid: int = 101,
    research_pid: int = 102,
) -> None:
    controller._write_state(
        {
            "status": "STARTED",
            "managed_run_id": managed_run_id,
            "dashboard_port": 8080,
            "evaluation_execution": "docker_worker",
            "components": [
                {
                    "id": "dashboard",
                    "status": "STARTED",
                    "pid": dashboard_pid,
                    "identity_markers": ["dashboard-owned"],
                },
                {
                    "id": "research_worker",
                    "status": "STARTED",
                    "pid": research_pid,
                    "identity_markers": ["research-owned", managed_run_id],
                },
                {
                    "id": "evaluation_backend",
                    "status": "CONFIGURED",
                    "mode": "docker_worker",
                    "active_jobs": 0,
                    "queued_jobs": 0,
                },
            ],
        }
    )


def test_status_recovers_live_processes_after_controller_recreation(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    first = SystemController(state_dir=state, project_root=tmp_path)
    _managed_state(first)

    recovered = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid in {101, 102},
    )

    payload = recovered.status()

    assert payload["status"] == "RUNNING"
    components = {
        item["id"]: item
        for item in payload["components"]
        if isinstance(item, dict)
    }
    assert components["dashboard"]["status"] == "RUNNING"
    assert components["dashboard"]["alive"] is True
    assert components["research_worker"]["status"] == "RUNNING"
    assert components["research_worker"]["alive"] is True
    assert components["evaluation_backend"]["status"] == "READY"


def test_start_blocks_duplicate_after_controller_recreation(tmp_path: Path) -> None:
    state = tmp_path / "state"
    first = SystemController(state_dir=state, project_root=tmp_path)
    _managed_state(first)
    spawned: list[list[str]] = []
    recovered = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_factory=lambda command, cwd: spawned.append(command),  # type: ignore[arg-type]
        process_probe=lambda pid, markers: pid in {101, 102},
    )

    result = recovered.start(
        SystemLaunchConfig(
            source_path="missing.py",
            data_path="missing.parquet",
        )
    )

    assert result["status"] == "ALREADY_RUNNING"
    assert spawned == []


def test_stale_worker_state_from_previous_run_is_ignored(tmp_path: Path) -> None:
    state = tmp_path / "state"
    controller = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: False,
    )
    _managed_state(controller, managed_run_id="run-2")
    worker_state = state / "system" / "research_worker.json"
    worker_state.write_text(
        '{"managed_run_id":"run-1","role":"research","status":"SUCCEEDED"}',
        encoding="utf-8",
    )

    payload = controller.status()

    components = {
        item["id"]: item
        for item in payload["components"]
        if isinstance(item, dict)
    }
    assert components["research_worker"]["status"] == "EXITED"
    assert payload["status"] == "STOPPED"


def test_matching_terminal_worker_state_survives_controller_recreation(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    controller = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid == 101,
    )
    _managed_state(controller, managed_run_id="run-2")
    worker_state = state / "system" / "research_worker.json"
    worker_state.write_text(
        '{"managed_run_id":"run-2","role":"research","status":"SUCCEEDED"}',
        encoding="utf-8",
    )

    payload = controller.status()

    components = {
        item["id"]: item
        for item in payload["components"]
        if isinstance(item, dict)
    }
    assert components["research_worker"]["status"] == "SUCCEEDED"
    assert payload["status"] == "COMPLETED"


def test_status_cancels_only_expired_jobs_owned_by_dead_managed_run(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    controller = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: False,
    )
    _managed_state(controller, managed_run_id="run-1")
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("owned", {"managed_run_id": "run-1"}, max_attempts=2))
    queue.enqueue(Job("other", {"managed_run_id": "run-2"}, max_attempts=2))
    assert queue.claim(job_id="owned", lease_seconds=30) is not None
    assert queue.claim(job_id="other", lease_seconds=30) is not None
    with sqlite3.connect(queue.path) as connection:
        connection.execute(
            "UPDATE jobs SET lease_until=? WHERE job_id IN (?, ?)",
            ("2000-01-01T00:00:00+00:00", "owned", "other"),
        )
        connection.commit()

    payload = controller.status()

    assert queue.get("owned").status is JobStatus.CANCELLED
    assert queue.get("owned").error_class == "OwnerExited"
    assert queue.get("other").status is JobStatus.RUNNING
    recovery = payload["recovery"]
    assert recovery["reconciled_jobs"] == ["owned"]
    assert recovery["cancelled_orphaned_jobs"] == ["owned"]


def test_recovered_stop_terminates_owned_processes_and_owned_docker_jobs_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = tmp_path / "state"
    first = SystemController(state_dir=state, project_root=tmp_path)
    _managed_state(first, managed_run_id="run-1")
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("owned", {"managed_run_id": "run-1"}, max_attempts=2))
    queue.enqueue(Job("other", {"managed_run_id": "run-2"}, max_attempts=2))
    owned = queue.claim(job_id="owned", lease_seconds=30)
    other = queue.claim(job_id="other", lease_seconds=30)
    assert owned is not None and other is not None
    terminated: list[tuple[int, tuple[str, ...]]] = []
    commands: list[list[str]] = []
    monkeypatch.setattr(
        controller_module.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    recovered = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid in {101, 102},
        process_terminator=lambda pid, markers: (
            terminated.append((pid, markers)) or True
        ),
        command_runner=lambda command, cwd: (
            commands.append(command) or (0, "")
        ),
    )

    result = recovered.stop()

    assert result["status"] == "STOPPED"
    assert {pid for pid, _ in terminated} == {101, 102}
    owned_name = docker_evaluation_container_name("owned", owned.attempt)
    other_name = docker_evaluation_container_name("other", other.attempt)
    assert ["docker", "rm", "-f", owned_name] in commands
    assert ["docker", "rm", "-f", other_name] not in commands
    assert queue.get("owned").status is JobStatus.CANCELLED
    assert queue.get("other").status is JobStatus.RUNNING




def test_recreated_controller_reports_active_owned_job_then_stops_it_safely(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = tmp_path / "state"
    first = SystemController(state_dir=state, project_root=tmp_path)
    _managed_state(first, managed_run_id="run-restart")
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("owned-live", {"managed_run_id": "run-restart"}, max_attempts=2))
    queue.enqueue(Job("foreign-live", {"managed_run_id": "run-other"}, max_attempts=2))
    owned = queue.claim(job_id="owned-live", lease_seconds=60)
    foreign = queue.claim(job_id="foreign-live", lease_seconds=60)
    assert owned is not None and foreign is not None

    commands: list[list[str]] = []
    terminated: list[int] = []
    monkeypatch.setattr(
        controller_module.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    recovered = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid in {101, 102},
        process_terminator=lambda pid, markers: (terminated.append(pid) or True),
        command_runner=lambda command, cwd: (commands.append(command) or (0, "")),
    )

    status = recovered.status()

    assert status["status"] == "RUNNING"
    components = {
        item["id"]: item
        for item in status["components"]
        if isinstance(item, dict)
    }
    assert components["evaluation_backend"]["active_jobs"] == 1
    assert components["evaluation_backend"]["queued_jobs"] == 0
    assert len(status["runtime"]["evaluation"]["active_jobs"]) == 1
    assert status["runtime"]["orders_enabled"] is False

    result = recovered.stop()

    assert result["status"] == "STOPPED"
    assert set(terminated) == {101, 102}
    owned_name = docker_evaluation_container_name("owned-live", owned.attempt)
    foreign_name = docker_evaluation_container_name("foreign-live", foreign.attempt)
    assert ["docker", "rm", "-f", owned_name] in commands
    assert ["docker", "rm", "-f", foreign_name] not in commands
    assert queue.get("owned-live").status is JobStatus.CANCELLED
    assert queue.get("foreign-live").status is JobStatus.RUNNING

    stopped = recovered.status()
    assert stopped["status"] == "STOPPED"
    assert stopped["runtime"]["orders_enabled"] is False


def test_aggregate_status_reports_degraded_when_dashboard_is_lost(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    controller = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid == 102,
    )
    _managed_state(controller)

    payload = controller.status()

    assert payload["status"] == "DEGRADED"



def _running_autoresearch(state: Path, *, research_run_id: str = "research-1") -> None:
    system = state / "system"
    system.mkdir(parents=True, exist_ok=True)
    (system / "autoresearch.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "research_run_id": research_run_id,
                "current_generation": 2,
                "current_phase": "BACKTESTING",
                "completed_generations": 1,
                "requested_generations": 3,
                "last_event": "evaluation_started",
                "last_event_at": "2026-09-26T00:00:00+00:00",
                "orders_enabled": False,
                "generations": [],
            }
        ),
        encoding="utf-8",
    )
    EvidenceStore(state).append(
        "run",
        f"run:{research_run_id}",
        {
            "research_run_id": research_run_id,
            "requested_generations": 3,
            "seed": 0,
        },
    )


def test_dead_research_owner_marks_run_interrupted_and_closes_evidence(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    controller = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid == 101,
    )
    _managed_state(controller, managed_run_id="managed-1")
    _running_autoresearch(state)
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("queued-owned", {"managed_run_id": "managed-1"}, max_attempts=2))

    payload = controller.status()

    assert payload["status"] == "INTERRUPTED"
    assert queue.get("queued-owned").status is JobStatus.CANCELLED
    assert queue.get("queued-owned").error_class == "OwnerExited"
    runtime = payload["runtime"]
    assert runtime["research"]["status"] == "INTERRUPTED"
    assert runtime["evidence"]["status"] == "INTERRUPTED"
    assert runtime["evidence"]["closed"] is True
    recovery = payload["recovery"]
    assert recovery["cancelled_orphaned_jobs"] == ["queued-owned"]
    assert recovery["interrupted_research_run_id"] == "research-1"
    events = [
        json.loads(line)
        for line in (state / "system" / "recovery-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert events[-1]["event"] == "INTERRUPTED"
    assert events[-1]["origin"]["research_run_id"] == "research-1"


def test_live_evaluation_lease_prevents_premature_interruption(tmp_path: Path) -> None:
    state = tmp_path / "state"
    controller = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid == 101,
    )
    _managed_state(controller, managed_run_id="managed-1")
    _running_autoresearch(state)
    queue = PersistentJobQueue(state)
    queue.enqueue(Job("running-owned", {"managed_run_id": "managed-1"}, max_attempts=2))
    assert queue.claim(job_id="running-owned", lease_seconds=60) is not None

    payload = controller.status()

    assert payload["status"] == "DEGRADED"
    assert queue.get("running-owned").status is JobStatus.RUNNING
    assert payload["runtime"]["research"]["status"] == "RUNNING"
    assert payload["runtime"]["evidence"]["status"] == "OPEN"


def test_start_after_interruption_creates_fresh_managed_run_with_lineage(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    first = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid == 101,
    )
    _managed_state(first, managed_run_id="managed-old")
    _running_autoresearch(state, research_run_id="research-old")
    assert first.status()["status"] == "INTERRUPTED"

    (tmp_path / "strategy.py").write_text("strategy", encoding="utf-8")
    (tmp_path / "data.parquet").write_bytes(b"fixture")
    terminated: list[int] = []
    spawned: list[list[str]] = []

    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

    recovered = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid == 101,
        process_terminator=lambda pid, markers: (terminated.append(pid) or True),
        process_factory=lambda command, cwd: (
            spawned.append(command) or FakeProcess(200 + len(spawned))
        ),
    )
    recovered.preflight = lambda config: PreflightReport("READY", (), ())  # type: ignore[method-assign]

    result = recovered.start(
        SystemLaunchConfig(source_path="strategy.py", data_path="data.parquet")
    )

    assert result["status"] == "STARTED"
    assert terminated == [101]
    assert len(spawned) == 2
    assert result["managed_run_id"] != "managed-old"
    assert result["restarted_from"]["managed_run_id"] == "managed-old"
    assert result["restarted_from"]["research_run_id"] == "research-old"
    events = [
        json.loads(line)
        for line in (state / "system" / "recovery-events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert events[-1]["event"] == "RESTARTED"
    assert events[-1]["managed_run_id"] == "managed-old"
    assert events[-1]["replacement_managed_run_id"] == result["managed_run_id"]



def test_status_returns_consistent_runtime_schema_when_stopped(tmp_path: Path) -> None:
    state = tmp_path / "state"
    controller = SystemController(state_dir=state, project_root=tmp_path)

    payload = controller.status()

    assert payload["status"] == "STOPPED"
    assert payload["components"] == []
    runtime = payload["runtime"]
    assert runtime["schema_version"] == 2
    assert runtime["system"]["status"] == "STOPPED"
    assert runtime["system"]["components"] == []
    assert runtime["research"]["status"] == "NOT_STARTED"
    assert runtime["orders_enabled"] is False
    assert not state.exists()


def test_status_runtime_system_view_matches_reconciled_components(tmp_path: Path) -> None:
    state = tmp_path / "state"
    first = SystemController(state_dir=state, project_root=tmp_path)
    _managed_state(first, managed_run_id="run-typed")
    recovered = SystemController(
        state_dir=state,
        project_root=tmp_path,
        process_probe=lambda pid, markers: pid in {101, 102},
    )

    payload = recovered.status()

    runtime = payload["runtime"]
    assert runtime["system"]["status"] == payload["status"] == "RUNNING"
    assert runtime["system"]["managed_run_id"] == "run-typed"
    top = {
        item["id"]: item["status"]
        for item in payload["components"]
        if isinstance(item, dict)
    }
    nested = {
        item["id"]: item["status"]
        for item in runtime["system"]["components"]
    }
    assert nested == top
