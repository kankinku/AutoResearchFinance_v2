from __future__ import annotations

from pathlib import Path

import runtime.system_controller as controller_module
from runtime.system_controller import PreflightReport, SystemController, SystemLaunchConfig


def test_preflight_returns_actionable_blockers_for_missing_inputs_and_docker(
    tmp_path: Path, monkeypatch
) -> None:
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
    assert {"strategy_source", "market_data", "docker_cli"}.issubset(issue_ids)
    assert any("Docker Desktop" in issue.action for issue in report.issues)


def test_start_does_not_spawn_processes_when_preflight_is_blocked(tmp_path: Path) -> None:
    controller = SystemController(state_dir=tmp_path / "state", project_root=tmp_path)
    spawned: list[list[str]] = []
    controller._process_factory = lambda command, cwd: spawned.append(command)  # type: ignore[assignment]

    result = controller.start(
        SystemLaunchConfig(source_path="missing.py", data_path="missing.parquet")
    )

    assert result["status"] == "BLOCKED"
    assert spawned == []


def test_start_launches_dashboard_research_and_docker_backtest_after_ready_preflight(
    tmp_path: Path,
) -> None:
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
        SystemLaunchConfig(source_path="strategy.py", data_path="data.parquet")
    )

    assert result["status"] == "STARTED"
    assert {item["status"] for item in result["components"]} == {"STARTED"}
    assert {item["id"] for item in result["components"]} == {
        "dashboard",
        "research_worker",
        "backtest_worker",
    }
    assert len(spawned) == 3
    assert any("system_worker" in part for command in spawned for part in command)
    assert any("docker" == command[0] for command in spawned)
