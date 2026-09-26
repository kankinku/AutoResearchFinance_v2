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
