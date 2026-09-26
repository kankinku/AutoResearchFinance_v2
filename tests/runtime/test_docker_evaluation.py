from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import runtime.docker_evaluation as docker_module
from runtime.docker_evaluation import DockerEvaluationRunner, DockerWorkerTimeout


def test_docker_evaluation_command_isolated_and_mounts_shared_state(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    runner = DockerEvaluationRunner(image="quant-worker:test")

    command, cleanup, name = runner.build_command(
        project_root=tmp_path,
        state_dir=state,
        job_id="evaluation-attempt-1",
        queue_attempt=2,
        lease_seconds=30,
    )

    assert command[:2] == ["docker", "run"]
    assert "--network" in command and command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert "--cap-drop" in command and command[command.index("--cap-drop") + 1] == "ALL"
    assert "--security-opt" in command
    assert f"type=bind,source={tmp_path.resolve()},target=/workspace,readonly" in command
    assert f"type=bind,source={state.resolve()},target=/workspace/state" in command
    assert "--role" in command
    assert command[command.index("--role") + 1] == "evaluation-job"
    assert command[command.index("--job-id") + 1] == "evaluation-attempt-1"
    assert name.endswith("-2")
    assert cleanup == ["docker", "rm", "-f", name]


def test_docker_evaluation_runner_passes_timeout_and_cleanup_to_process(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    captured: dict[str, object] = {}

    def process(
        command: list[str],
        timeout: float,
        cleanup: list[str],
    ) -> tuple[int, str, str]:
        captured["command"] = command
        captured["timeout"] = timeout
        captured["cleanup"] = cleanup
        return 0, "ok", ""

    result = DockerEvaluationRunner(
        image="quant-worker:test",
        process=process,
    ).run(
        project_root=tmp_path,
        state_dir=state,
        job_id="evaluation-1",
        queue_attempt=1,
        lease_seconds=15,
        timeout=12,
    )

    assert result.returncode == 0
    assert result.stdout == "ok"
    assert captured["timeout"] == 12
    cleanup = captured["cleanup"]
    assert isinstance(cleanup, list)
    assert cleanup[:3] == ["docker", "rm", "-f"]


def test_subprocess_timeout_forces_container_cleanup(monkeypatch) -> None:
    cleanup_calls: list[list[str]] = []

    class FakeProcess:
        returncode = 124
        killed = False

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            if timeout is not None:
                raise subprocess.TimeoutExpired(["docker", "run"], timeout)
            return "", ""

        def kill(self) -> None:
            self.killed = True

    process = FakeProcess()
    monkeypatch.setattr(
        docker_module.subprocess,
        "Popen",
        lambda *args, **kwargs: process,
    )

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        cleanup_calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(docker_module.subprocess, "run", fake_run)

    with pytest.raises(DockerWorkerTimeout, match="timed out"):
        DockerEvaluationRunner._subprocess(
            ["docker", "run", "--name", "quant-eval-job"],
            1,
            ["docker", "rm", "-f", "quant-eval-job"],
        )

    assert cleanup_calls == [["docker", "rm", "-f", "quant-eval-job"]]
    assert process.killed is True
