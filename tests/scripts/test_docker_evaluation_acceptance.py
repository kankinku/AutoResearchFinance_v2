from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import scripts.verify_docker_evaluation as acceptance


def test_docker_acceptance_check_only_reports_ready(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        acceptance.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="ok",
            stderr="",
        ),
    )

    exit_code = acceptance.main(
        [
            "--project-root",
            str(tmp_path),
            "--image",
            "quant-worker:test",
            "--check-only",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"status": "READY"' in output
    assert '"orders_enabled": false' in output


def test_docker_acceptance_full_run_uses_isolated_executor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        acceptance,
        "docker_prerequisites",
        lambda image, project_root: {
            "docker_cli": "PASS",
            "docker_engine": "PASS",
            "docker_image": "PASS",
        },
    )

    class FakeExecutor:
        def __init__(self, state_dir: Path, **kwargs: object) -> None:
            captured["state_dir"] = state_dir
            captured["init"] = kwargs

        def run(self, evaluator: object, **kwargs: object) -> dict[str, object]:
            captured["evaluator"] = evaluator
            captured["run"] = kwargs
            return {"status": "COMPLETED", "candidate_count": 1}

    monkeypatch.setattr(acceptance, "QueuedEvaluationExecutor", FakeExecutor)

    result = acceptance.run_acceptance(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        image="quant-worker:test",
        source_path="strategy.yaml",
        data_path="bars.parquet",
    )

    init = captured["init"]
    assert init["execution_mode"] == "docker_worker"
    assert init["docker_image"] == "quant-worker:test"
    assert str(init["managed_run_id"]).startswith("host-acceptance-")
    run = captured["run"]
    assert run["count"] == 1
    assert run["min_annual_trades"] == 0
    assert result["status"] == "PASS"
    assert result["orders_enabled"] is False


def test_docker_acceptance_blocks_when_docker_is_missing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: None)

    exit_code = acceptance.main(
        [
            "--project-root",
            str(tmp_path),
            "--check-only",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert '"status": "BLOCKED"' in output
    assert "Docker CLI is not available" in output


def _write_build_contract(root: Path) -> None:
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "Dockerfile.worker").write_text(
        "FROM python:3.11-slim\n"
        "WORKDIR /workspace\n"
        "ENTRYPOINT [\"python\", \"-m\", \"runtime.system_worker\"]\n",
        encoding="utf-8",
    )
    (root / ".dockerignore").write_text(
        ".env\n.env.*\n.git\nstate\n.venv\n",
        encoding="utf-8",
    )


def test_worker_build_contract_and_command_are_static_and_deterministic(tmp_path: Path) -> None:
    _write_build_contract(tmp_path)

    checks = acceptance.worker_build_contract(
        "quant-worker:test", project_root=tmp_path
    )
    command = acceptance.docker_build_command(
        "quant-worker:test",
        project_root=tmp_path,
        docker_executable="C:/Program Files/Docker/docker.exe",
    )

    assert checks == {
        "image_reference": "PASS",
        "worker_dockerfile": "PASS",
        "dockerignore": "PASS",
    }
    assert command == [
        "C:/Program Files/Docker/docker.exe",
        "build",
        "--tag",
        "quant-worker:test",
        "--file",
        "runtime/Dockerfile.worker",
        ".",
    ]


def test_check_build_context_does_not_require_docker(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_build_contract(tmp_path)
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: None)

    exit_code = acceptance.main(
        [
            "--project-root",
            str(tmp_path),
            "--image",
            "quant-worker:test",
            "--check-build-context",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"status": "STATIC_READY"' in output
    assert '"image_built": false' in output
    assert '"dockerignore": "PASS"' in output


def test_build_image_runs_engine_build_and_inspect(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_build_contract(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: "/usr/bin/docker")

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(command))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(acceptance.subprocess, "run", fake_run)

    checks = acceptance.build_worker_image(
        "quant-worker:test", project_root=tmp_path
    )

    assert calls == [
        ["/usr/bin/docker", "info", "--format", "{{.ServerVersion}}"],
        [
            "/usr/bin/docker",
            "build",
            "--tag",
            "quant-worker:test",
            "--file",
            "runtime/Dockerfile.worker",
            ".",
        ],
        ["/usr/bin/docker", "image", "inspect", "quant-worker:test"],
    ]
    assert checks["docker_build"] == "PASS"
    assert checks["docker_image"] == "PASS"


def test_build_image_blocks_when_docker_is_missing(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_build_contract(tmp_path)
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: None)

    exit_code = acceptance.main(
        [
            "--project-root",
            str(tmp_path),
            "--image",
            "quant-worker:test",
            "--build-image",
            "--check-only",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert '"status": "BLOCKED"' in output
    assert "Docker CLI is not available" in output
    assert '"orders_enabled": false' in output
