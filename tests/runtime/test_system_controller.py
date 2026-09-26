from __future__ import annotations

from pathlib import Path

import runtime.system_controller as controller_module
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
