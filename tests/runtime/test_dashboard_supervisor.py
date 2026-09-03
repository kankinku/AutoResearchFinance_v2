from pathlib import Path

from runtime.dashboard_supervisor import DashboardSupervisorConfig, dashboard_command


def test_dashboard_supervisor_uses_local_read_only_dashboard_command(tmp_path: Path) -> None:
    config = DashboardSupervisorConfig(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        env_file=tmp_path / ".env",
        host="127.0.0.1",
        port=8080,
    )

    command = dashboard_command(config)

    assert command[1:3] == ["cli.py", "dashboard"]
    assert "--host" in command and command[command.index("--host") + 1] == "127.0.0.1"
    assert "--port" in command and command[command.index("--port") + 1] == "8080"
    assert "--state-dir" in command
    assert "--env-file" in command
    assert "--mode" not in command


def test_dashboard_supervisor_log_path_is_under_state(tmp_path: Path) -> None:
    config = DashboardSupervisorConfig(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        env_file=tmp_path / ".env",
        host="localhost",
        port=8080,
    )

    assert config.log_path == tmp_path / "state" / "system" / "dashboard-supervisor.log"
