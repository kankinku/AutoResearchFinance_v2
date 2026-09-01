from __future__ import annotations

from pathlib import Path

from runtime.docker_runner import DockerLeanRunner
from runtime.lean_worker import LeanWorkerSpec


def test_docker_command_is_isolated_and_mounts_data_read_only(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "run-1"
    data_dir.mkdir()
    output_dir.mkdir()
    command = DockerLeanRunner(image="lean-worker:test").build_command(
        LeanWorkerSpec(data_dir, output_dir), ["dotnet", "Quant.dll"]
    )

    assert "--network" in command and command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert "--cap-drop" in command and command[command.index("--cap-drop") + 1] == "ALL"
    assert f"{data_dir.resolve()}:/input:ro" in command
    assert f"{output_dir.resolve()}:/output:rw" in command
    assert "dotnet" in command and "Quant.dll" in command


def test_runner_uses_injected_process_and_returns_result(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "run-1"
    data_dir.mkdir()
    output_dir.mkdir()
    calls: list[list[str]] = []

    def process(command: list[str], timeout: float) -> tuple[int, str, str]:
        calls.append(command)
        assert timeout == 3.0
        return 0, "ok", ""

    runner = DockerLeanRunner(image="lean-worker:test", process=process)
    result = runner.run(LeanWorkerSpec(data_dir, output_dir), ["worker"], timeout=3.0)

    assert result.returncode == 0
    assert result.stdout == "ok"
    assert calls
