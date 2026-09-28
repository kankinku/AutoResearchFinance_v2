from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
            return {
                "status": "COMPLETED",
                "candidate_count": 1,
                "research_run_id": "research-1",
                "attempt_id": "attempt-1",
            }

    monkeypatch.setattr(acceptance, "QueuedEvaluationExecutor", FakeExecutor)

    class FakeQueue:
        def __init__(self, state_dir: Path) -> None:
            captured["queue_state_dir"] = state_dir

        def jobs_for_run(self, managed_run_id: str):  # type: ignore[no-untyped-def]
            captured["queue_managed_run_id"] = managed_run_id
            return (
                SimpleNamespace(
                    job_id="evaluation-host-acceptance",
                    status=acceptance.JobStatus.SUCCEEDED,
                    attempt=1,
                ),
            )

    monkeypatch.setattr(acceptance, "PersistentJobQueue", FakeQueue)

    def fake_verify_evidence(**kwargs: object) -> dict[str, object]:
        captured["evidence"] = kwargs
        return {
            "status": "VERIFIED",
            "event_id": "attempt:attempt-1",
            "execution_mode": "docker_worker",
            "isolated": True,
            "timeout_enforced": True,
            "job_id": kwargs["job_id"],
            "managed_run_id": kwargs["managed_run_id"],
        }

    monkeypatch.setattr(acceptance, "verify_docker_evidence", fake_verify_evidence)

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
    assert result["queue_status"] == "SUCCEEDED"
    assert result["durable_job_count"] == 1
    assert result["evidence_verified"] is True
    evidence_call = captured["evidence"]
    assert evidence_call["research_run_id"] == "research-1"
    assert evidence_call["attempt_id"] == "attempt-1"
    assert evidence_call["job_id"] == "evaluation-host-acceptance"
    assert evidence_call["managed_run_id"] == init["managed_run_id"]
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


def test_prepare_acceptance_fixture_uses_checked_in_strategy_and_development_parquet(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    normalized = project / "strategies" / "normalized"
    normalized.mkdir(parents=True)
    (normalized / "fixture.json").write_text(
        "{\"schema_version\": 1}",
        encoding="utf-8",
    )
    state = project / "state" / "docker-acceptance"

    source_path, data_path = acceptance.prepare_acceptance_fixture(
        project_root=project,
        state_dir=state,
    )

    assert source_path == "strategies/normalized/fixture.json"
    assert data_path == "state/docker-acceptance/host-fixture/bars.parquet"
    dataset = acceptance.ParquetDataProvider.read(project / data_path)
    assert dataset.zone is acceptance.DataZone.DEVELOPMENT
    assert dataset.version == "docker-host-acceptance-v1"
    assert len(dataset.bars) == 80
    assert {bar.symbol for bar in dataset.bars} == {"QQQ"}


def test_prepare_acceptance_fixture_rejects_state_outside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "strategies" / "normalized").mkdir(parents=True)

    try:
        acceptance.prepare_acceptance_fixture(
            project_root=project,
            state_dir=tmp_path / "outside-state",
        )
    except RuntimeError as exc:
        assert "inside project root" in str(exc)
    else:
        raise AssertionError("outside state_dir must be rejected")


def test_single_job_acceptance_rejects_missing_or_non_succeeded_durable_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeExecutor:
        def __init__(self, state_dir: Path, **kwargs: object) -> None:
            pass

        def run(self, evaluator: object, **kwargs: object) -> dict[str, object]:
            return {"status": "COMPLETED", "candidate_count": 1}

    class EmptyQueue:
        def __init__(self, state_dir: Path) -> None:
            pass

        def jobs_for_run(self, managed_run_id: str):  # type: ignore[no-untyped-def]
            return ()

    monkeypatch.setattr(acceptance, "QueuedEvaluationExecutor", FakeExecutor)
    monkeypatch.setattr(acceptance, "PersistentJobQueue", EmptyQueue)

    try:
        acceptance.run_acceptance(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            image="quant-worker:test",
            source_path="strategy.json",
            data_path="bars.parquet",
        )
    except RuntimeError as exc:
        assert "exactly one durable job" in str(exc)
    else:
        raise AssertionError("missing durable job must fail acceptance")


def _seed_docker_attempt_evidence(
    state: Path,
    *,
    research_run_id: str = "research-1",
    attempt_id: str = "attempt-1",
    job_id: str = "evaluation-attempt-1",
    managed_run_id: str = "managed-1",
    isolated: bool = True,
) -> None:
    store = acceptance.EvidenceStore(state)
    store.append(
        "run",
        f"run:{research_run_id}",
        {
            "research_run_id": research_run_id,
            "requested_generations": 1,
            "seed": 0,
        },
    )
    store.append(
        "attempt",
        f"attempt:{attempt_id}",
        {
            "research_run_id": research_run_id,
            "attempt_id": attempt_id,
            "generation": 1,
            "status": "COMPLETED",
            "execution": {
                "worker": {
                    "execution_mode": "docker_worker",
                    "isolated": isolated,
                    "timeout_enforced": True,
                    "job_id": job_id,
                    "managed_run_id": managed_run_id,
                }
            },
            "candidates": [],
        },
    )


def test_verify_docker_evidence_links_attempt_to_job_and_managed_run(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _seed_docker_attempt_evidence(state)

    result = acceptance.verify_docker_evidence(
        state_dir=state,
        research_run_id="research-1",
        attempt_id="attempt-1",
        job_id="evaluation-attempt-1",
        managed_run_id="managed-1",
    )

    assert result == {
        "status": "VERIFIED",
        "event_id": "attempt:attempt-1",
        "execution_mode": "docker_worker",
        "isolated": True,
        "timeout_enforced": True,
        "job_id": "evaluation-attempt-1",
        "managed_run_id": "managed-1",
    }


def test_verify_docker_evidence_rejects_nonisolated_attempt(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _seed_docker_attempt_evidence(state, isolated=False)

    try:
        acceptance.verify_docker_evidence(
            state_dir=state,
            research_run_id="research-1",
            attempt_id="attempt-1",
            job_id="evaluation-attempt-1",
            managed_run_id="managed-1",
        )
    except RuntimeError as exc:
        assert "isolated" in str(exc)
    else:
        raise AssertionError("nonisolated evidence must fail Docker acceptance")


def test_verify_docker_evidence_rejects_job_identity_mismatch(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _seed_docker_attempt_evidence(state)

    try:
        acceptance.verify_docker_evidence(
            state_dir=state,
            research_run_id="research-1",
            attempt_id="attempt-1",
            job_id="evaluation-other",
            managed_run_id="managed-1",
        )
    except RuntimeError as exc:
        assert "job_id" in str(exc)
    else:
        raise AssertionError("mismatched job identity must fail Docker acceptance")


def test_verify_docker_evidence_rejects_missing_attempt(tmp_path: Path) -> None:
    state = tmp_path / "state"
    _seed_docker_attempt_evidence(state)

    try:
        acceptance.verify_docker_evidence(
            state_dir=state,
            research_run_id="research-1",
            attempt_id="missing-attempt",
            job_id="evaluation-attempt-1",
            managed_run_id="managed-1",
        )
    except RuntimeError as exc:
        assert "uniquely persisted" in str(exc)
    else:
        raise AssertionError("missing evidence attempt must fail Docker acceptance")


def test_canonical_evaluator_persists_verifiable_docker_execution_evidence(
    tmp_path: Path,
) -> None:
    strategy = tmp_path / "strategy.yaml"
    strategy.write_text(
        "schema_version: 1\n"
        "id: docker-evidence-fixture\n"
        "family: trend\n"
        "generation: 0\n"
        "indicators:\n"
        "  fast: {type: SMA, period: 2}\n"
        "entry: {logic: AND, conditions: [{op: greater_than, left: close, value: 0}]}\n"
        "exit: {logic: AND, conditions: [{op: less_than, left: close, value: 0}]}\n"
        "risk: {stop_loss_pct: 0, take_profit_pct: 0}\n",
        encoding="utf-8",
    )
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = tuple(
        acceptance.Bar(
            start + timedelta(days=index),
            "QQQ",
            100.0 + index,
            101.0 + index,
            99.0 + index,
            100.0 + index,
            1_000.0,
        )
        for index in range(8)
    )
    acceptance.ParquetDataProvider.write(
        tmp_path / "bars.parquet",
        acceptance.MarketDataSet("docker-evidence-v1", acceptance.DataZone.DEVELOPMENT, bars),
    )
    state = tmp_path / "state"
    result = acceptance.run_local_evaluation(
        project_root=tmp_path,
        state_dir=state,
        source_path="strategy.yaml",
        data_path="bars.parquet",
        count=1,
        min_trades=0,
        min_annual_trades=0,
        attempt_id="attempt-real",
        execution_context={
            "job_id": "evaluation-attempt-real",
            "queue_attempt": 1,
            "max_attempts": 1,
            "execution_mode": "docker_worker",
            "isolated": True,
            "timeout_enforced": True,
            "lease_seconds": 60.0,
            "managed_run_id": "managed-real",
        },
    )

    evidence = acceptance.verify_docker_evidence(
        state_dir=state,
        research_run_id=str(result["research_run_id"]),
        attempt_id=str(result["attempt_id"]),
        job_id="evaluation-attempt-real",
        managed_run_id="managed-real",
    )

    assert evidence["status"] == "VERIFIED"
    assert evidence["execution_mode"] == "docker_worker"
    assert evidence["isolated"] is True
    assert evidence["timeout_enforced"] is True



def test_timeout_probe_command_is_hardened() -> None:
    command, cleanup = acceptance.timeout_probe_command(
        "quant-worker:test",
        container_name="quant-eval-timeout-probe-1",
        sleep_seconds=5.0,
        docker_executable="docker",
    )

    assert command[:2] == ["docker", "run"]
    assert "--network" in command and command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert "--cap-drop" in command and command[command.index("--cap-drop") + 1] == "ALL"
    assert "--entrypoint" in command and command[command.index("--entrypoint") + 1] == "python"
    assert cleanup == ["docker", "rm", "-f", "quant-eval-timeout-probe-1"]


def test_timeout_acceptance_persists_timed_out_and_verifies_cleanup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = tmp_path / "state"
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: "/usr/bin/docker")

    def fake_timeout(command, timeout, cleanup):  # type: ignore[no-untyped-def]
        assert command[0] == "/usr/bin/docker"
        assert cleanup[:3] == ["/usr/bin/docker", "rm", "-f"]
        raise acceptance.DockerWorkerTimeout("forced timeout")

    monkeypatch.setattr(
        acceptance.DockerEvaluationRunner,
        "_subprocess",
        staticmethod(fake_timeout),
    )
    monkeypatch.setattr(
        acceptance.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="not found"),
    )

    result = acceptance.run_timeout_acceptance(
        project_root=tmp_path,
        state_dir=state,
        image="quant-worker:test",
        timeout_seconds=0.1,
    )

    assert result["status"] == "PASS"
    assert result["probe"] == "timeout"
    assert result["queue_status"] == "TIMED_OUT"
    assert result["queue_attempt"] == 1
    assert result["max_attempts"] == 1
    assert result["error_class"] == "TimeoutError"
    assert result["container_removed"] is True
    assert result["timeout_enforced"] is True
    assert result["orders_enabled"] is False


def test_timeout_acceptance_cli_blocks_without_docker(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: None)

    exit_code = acceptance.main(
        [
            "--project-root",
            str(tmp_path),
            "--verify-timeout",
            "--timeout-seconds",
            "0.1",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert '"status": "BLOCKED"' in output
    assert "Docker CLI is not available" in output
    assert '"orders_enabled": false' in output



def test_retry_exhaustion_acceptance_retries_timeout_until_terminal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = tmp_path / "state"
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: "/usr/bin/docker")
    calls = 0

    def fake_timeout(command, timeout, cleanup):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        assert cleanup[:3] == ["/usr/bin/docker", "rm", "-f"]
        raise acceptance.DockerWorkerTimeout("forced timeout")

    monkeypatch.setattr(
        acceptance.DockerEvaluationRunner,
        "_subprocess",
        staticmethod(fake_timeout),
    )
    monkeypatch.setattr(
        acceptance.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="not found"),
    )

    result = acceptance.run_retry_exhaustion_acceptance(
        project_root=tmp_path,
        state_dir=state,
        image="quant-worker:test",
        timeout_seconds=0.1,
        max_retries=2,
    )

    assert calls == 3
    assert result["status"] == "PASS"
    assert result["queue_status"] == "RETRY_EXHAUSTED"
    assert result["queue_attempt"] == 3
    assert result["max_attempts"] == 3
    assert result["max_retries"] == 2
    assert result["error_class"] == "TimeoutError"
    assert result["cleanup_count"] == 3
    assert result["removed_container_count"] == 3
    assert result["timeout_retryable"] is True
    assert result["worker_process_retryable"] is True
    assert result["deterministic_value_error_retryable"] is False
    assert result["timeout_enforced"] is True
    assert result["orders_enabled"] is False


def test_retry_exhaustion_requires_at_least_one_retry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: "/usr/bin/docker")

    try:
        acceptance.run_retry_exhaustion_acceptance(
            project_root=tmp_path,
            state_dir=tmp_path / "state",
            image="quant-worker:test",
            timeout_seconds=0.1,
            max_retries=0,
        )
    except RuntimeError as exc:
        assert "max_retries >= 1" in str(exc)
    else:
        raise AssertionError("retry exhaustion probe must require at least one retry")


def test_retry_exhaustion_cli_blocks_without_docker(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(acceptance.shutil, "which", lambda name: None)

    exit_code = acceptance.main(
        [
            "--project-root",
            str(tmp_path),
            "--verify-retry-exhaustion",
            "--timeout-seconds",
            "0.1",
            "--max-retries",
            "1",
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert '"status": "BLOCKED"' in output
    assert "Docker CLI is not available" in output
    assert '"orders_enabled": false' in output
