from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from core.data.contracts import Bar, DataZone, MarketDataSet
from core.data.parquet import ParquetDataProvider
from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from orchestration.evaluation_runner import run_local_evaluation
from runtime.docker_evaluation import (
    DockerEvaluationRunner,
    DockerWorkerTimeout,
    docker_evaluation_container_name,
)
from runtime.evaluation_executor import QueuedEvaluationExecutor, is_retryable_error
from runtime.persistent_queue import PersistentJobQueue
from runtime.process_lifecycle import spawn_managed_process
from runtime.queue import Job, JobStatus
from runtime.system_controller import SystemController

DEFAULT_IMAGE = "quant-autoresearch-worker:local"
WORKER_DOCKERFILE = Path("runtime/Dockerfile.worker")
_REQUIRED_DOCKERIGNORE = frozenset({".env", ".env.*", ".git", "state", ".venv"})


def worker_build_contract(image: str, *, project_root: Path) -> dict[str, str]:
    if not image or any(char.isspace() for char in image):
        raise RuntimeError("Docker image reference is invalid")
    dockerfile = project_root / WORKER_DOCKERFILE
    if not dockerfile.is_file():
        raise RuntimeError("worker Dockerfile is missing")
    try:
        dockerfile_text = dockerfile.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("worker Dockerfile could not be read") from exc
    required_fragments = (
        "FROM python:3.11-slim",
        "WORKDIR /workspace",
        "ENTRYPOINT [\"python\", \"-m\", \"runtime.system_worker\"]",
    )
    if any(fragment not in dockerfile_text for fragment in required_fragments):
        raise RuntimeError("worker Dockerfile contract is invalid")
    dockerignore = project_root / ".dockerignore"
    if not dockerignore.is_file():
        raise RuntimeError(".dockerignore is missing")
    try:
        ignored = {
            line.strip()
            for line in dockerignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
    except OSError as exc:
        raise RuntimeError(".dockerignore could not be read") from exc
    missing = _REQUIRED_DOCKERIGNORE - ignored
    if missing:
        raise RuntimeError("Docker build context does not exclude required local state")
    return {
        "image_reference": "PASS",
        "worker_dockerfile": "PASS",
        "dockerignore": "PASS",
    }


def docker_build_command(
    image: str,
    *,
    project_root: Path,
    docker_executable: str = "docker",
) -> list[str]:
    worker_build_contract(image, project_root=project_root)
    return [
        docker_executable,
        "build",
        "--tag",
        image,
        "--file",
        WORKER_DOCKERFILE.as_posix(),
        ".",
    ]


def build_worker_image(
    image: str,
    *,
    project_root: Path,
) -> dict[str, str]:
    contract = worker_build_contract(image, project_root=project_root)
    executable = shutil.which("docker")
    if not executable:
        raise RuntimeError("Docker CLI is not available")
    engine = subprocess.run(
        [executable, "info", "--format", "{{.ServerVersion}}"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if engine.returncode != 0:
        raise RuntimeError("docker_engine check failed")
    build = subprocess.run(
        docker_build_command(
            image,
            project_root=project_root,
            docker_executable=executable,
        ),
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if build.returncode != 0:
        raise RuntimeError("docker_build check failed")
    inspect = subprocess.run(
        [executable, "image", "inspect", image],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if inspect.returncode != 0:
        raise RuntimeError("docker_image check failed")
    return {
        **contract,
        "docker_cli": "PASS",
        "docker_engine": "PASS",
        "docker_build": "PASS",
        "docker_image": "PASS",
    }


def docker_prerequisites(
    image: str,
    *,
    project_root: Path,
) -> dict[str, str]:
    executable = shutil.which("docker")
    if not executable:
        raise RuntimeError("Docker CLI is not available")
    checks = (
        ([executable, "info", "--format", "{{.ServerVersion}}"], "docker_engine"),
        ([executable, "image", "inspect", image], "docker_image"),
    )
    result: dict[str, str] = {"docker_cli": "PASS"}
    for command, name in checks:
        try:
            completed = subprocess.run(
                command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"{name} check could not complete") from exc
        if completed.returncode != 0:
            raise RuntimeError(f"{name} check failed")
        result[name] = "PASS"
    return result


def prepare_acceptance_fixture(
    *,
    project_root: Path,
    state_dir: Path,
) -> tuple[str, str]:
    project = project_root.resolve()
    state = state_dir.resolve()
    if project != state and project not in state.parents:
        raise RuntimeError("acceptance fixture state_dir must be inside project root")
    strategies = sorted((project / "strategies" / "normalized").glob("*.json"))
    if not strategies:
        raise RuntimeError("no normalized strategy fixture is available")
    source = strategies[0]
    data = state / "host-fixture" / "bars.parquet"
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    bars = tuple(
        Bar(
            start + timedelta(days=index),
            "QQQ",
            100.0 + index * 0.25,
            102.0 + index * 0.25,
            98.0 + index * 0.25,
            99.0 + index * 0.25 + (1.5 if index % 5 == 0 else 0.0),
            1_000_000.0 + index,
        )
        for index in range(80)
    )
    ParquetDataProvider.write(
        data,
        MarketDataSet(
            "docker-host-acceptance-v1",
            DataZone.DEVELOPMENT,
            bars,
        ),
    )
    return (
        source.relative_to(project).as_posix(),
        data.relative_to(project).as_posix(),
    )


def verify_docker_evidence(
    *,
    state_dir: Path,
    research_run_id: str,
    attempt_id: str,
    job_id: str,
    managed_run_id: str,
) -> dict[str, object]:
    if not all((research_run_id, attempt_id, job_id, managed_run_id)):
        raise RuntimeError("docker evidence verification requires run/attempt/job identities")
    try:
        events = EvidenceStore(state_dir).events()
    except EvidenceIntegrityError as exc:
        raise RuntimeError("docker evidence store is not readable") from exc
    matches = [
        event
        for event in events
        if event.get("kind") == "attempt"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("research_run_id") == research_run_id
        and event["payload"].get("attempt_id") == attempt_id
    ]
    if len(matches) != 1:
        raise RuntimeError("docker evidence attempt was not uniquely persisted")
    payload = matches[0]["payload"]
    execution = payload.get("execution")
    worker = execution.get("worker") if isinstance(execution, dict) else None
    if not isinstance(worker, dict):
        raise RuntimeError("docker evidence worker metadata is missing")
    expected = {
        "execution_mode": "docker_worker",
        "isolated": True,
        "timeout_enforced": True,
        "job_id": job_id,
        "managed_run_id": managed_run_id,
    }
    for name, value in expected.items():
        if worker.get(name) != value:
            raise RuntimeError(f"docker evidence metadata mismatch: {name}")
    return {
        "status": "VERIFIED",
        "event_id": matches[0].get("id"),
        "execution_mode": "docker_worker",
        "isolated": True,
        "timeout_enforced": True,
        "job_id": job_id,
        "managed_run_id": managed_run_id,
    }



def timeout_probe_command(
    image: str,
    *,
    container_name: str,
    sleep_seconds: float,
    docker_executable: str = "docker",
) -> tuple[list[str], list[str]]:
    if sleep_seconds <= 0:
        raise RuntimeError("timeout probe sleep must be positive")
    command = [
        docker_executable,
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--cpus",
        "0.25",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "--entrypoint",
        "python",
        image,
        "-c",
        f"import time; time.sleep({sleep_seconds!r})",
    ]
    return command, [docker_executable, "rm", "-f", container_name]


def run_timeout_acceptance(
    *,
    project_root: Path,
    state_dir: Path,
    image: str,
    timeout_seconds: float,
) -> dict[str, object]:
    if timeout_seconds <= 0:
        raise RuntimeError("timeout_seconds must be positive")
    executable = shutil.which("docker")
    if not executable:
        raise RuntimeError("Docker CLI is not available")
    managed_run_id = f"host-timeout-{uuid4().hex}"
    job_id = f"timeout-probe-{uuid4().hex}"
    queue = PersistentJobQueue(state_dir)
    queue.enqueue(
        Job(
            job_id,
            {"role": "timeout-acceptance", "managed_run_id": managed_run_id},
            max_attempts=1,
        )
    )
    lease_seconds = max(timeout_seconds * 4.0, 2.0)
    claimed = queue.claim(job_id=job_id, lease_seconds=lease_seconds)
    if claimed is None:
        raise RuntimeError("timeout acceptance job could not be claimed")
    container_name = docker_evaluation_container_name(job_id, claimed.attempt)
    command, cleanup = timeout_probe_command(
        image,
        container_name=container_name,
        sleep_seconds=max(timeout_seconds * 20.0, 5.0),
        docker_executable=executable,
    )
    try:
        DockerEvaluationRunner._subprocess(command, timeout_seconds, cleanup)
    except DockerWorkerTimeout:
        queue.timeout(job_id, error_class="TimeoutError")
    else:
        raise RuntimeError("timeout probe unexpectedly completed before timeout")

    current = queue.get(job_id)
    if current.status is not JobStatus.TIMED_OUT:
        raise RuntimeError("timeout probe did not persist TIMED_OUT queue state")
    inspect = subprocess.run(
        [executable, "container", "inspect", container_name],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if inspect.returncode == 0:
        raise RuntimeError("timed out Docker container still exists after cleanup")
    return {
        "status": "PASS",
        "probe": "timeout",
        "job_id": job_id,
        "managed_run_id": managed_run_id,
        "queue_status": current.status.value,
        "queue_attempt": current.attempt,
        "max_attempts": current.max_attempts,
        "error_class": current.error_class,
        "cleanup_command": cleanup,
        "container_removed": True,
        "timeout_enforced": True,
        "orders_enabled": False,
    }


def run_retry_exhaustion_acceptance(
    *,
    project_root: Path,
    state_dir: Path,
    image: str,
    timeout_seconds: float,
    max_retries: int,
) -> dict[str, object]:
    if timeout_seconds <= 0:
        raise RuntimeError("timeout_seconds must be positive")
    if max_retries < 1:
        raise RuntimeError("retry exhaustion acceptance requires max_retries >= 1")
    executable = shutil.which("docker")
    if not executable:
        raise RuntimeError("Docker CLI is not available")
    managed_run_id = f"host-retry-{uuid4().hex}"
    job_id = f"retry-probe-{uuid4().hex}"
    max_attempts = max_retries + 1
    queue = PersistentJobQueue(state_dir)
    queue.enqueue(
        Job(
            job_id,
            {"role": "retry-exhaustion-acceptance", "managed_run_id": managed_run_id},
            max_attempts=max_attempts,
        )
    )
    cleanup_commands: list[list[str]] = []
    removed_containers: list[str] = []
    lease_seconds = max(timeout_seconds * 4.0, 2.0)

    while True:
        claimed = queue.claim(job_id=job_id, lease_seconds=lease_seconds)
        if claimed is None:
            raise RuntimeError("retry acceptance job could not be claimed")
        container_name = docker_evaluation_container_name(job_id, claimed.attempt)
        command, cleanup = timeout_probe_command(
            image,
            container_name=container_name,
            sleep_seconds=max(timeout_seconds * 20.0, 5.0),
            docker_executable=executable,
        )
        try:
            DockerEvaluationRunner._subprocess(command, timeout_seconds, cleanup)
        except DockerWorkerTimeout:
            queue.timeout(job_id, error_class="TimeoutError")
        else:
            raise RuntimeError("retry timeout probe unexpectedly completed")
        cleanup_commands.append(cleanup)

        inspect = subprocess.run(
            [executable, "container", "inspect", container_name],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if inspect.returncode == 0:
            raise RuntimeError("retry probe container still exists after cleanup")
        removed_containers.append(container_name)

        current = queue.get(job_id)
        if not is_retryable_error(current.error_class):
            raise RuntimeError("timeout probe was not classified as retryable")
        queue.retry_terminal(job_id)
        current = queue.get(job_id)
        if current.status is JobStatus.RETRY_EXHAUSTED:
            break
        if current.status is not JobStatus.QUEUED:
            raise RuntimeError("retry probe entered an invalid queue state")

    final = queue.get(job_id)
    if final.attempt != max_attempts:
        raise RuntimeError("retry exhaustion attempt count mismatch")
    if final.error_class != "TimeoutError":
        raise RuntimeError("retry exhaustion error class mismatch")
    if is_retryable_error("ValueError"):
        raise RuntimeError("deterministic ValueError must not be retryable")
    return {
        "status": "PASS",
        "probe": "retry_exhaustion",
        "job_id": job_id,
        "managed_run_id": managed_run_id,
        "queue_status": final.status.value,
        "queue_attempt": final.attempt,
        "max_attempts": final.max_attempts,
        "max_retries": max_retries,
        "error_class": final.error_class,
        "cleanup_count": len(cleanup_commands),
        "removed_container_count": len(removed_containers),
        "timeout_retryable": is_retryable_error("TimeoutError"),
        "worker_process_retryable": is_retryable_error("WorkerProcessError"),
        "deterministic_value_error_retryable": is_retryable_error("ValueError"),
        "timeout_enforced": True,
        "orders_enabled": False,
    }


def _wait_for_container_running(
    executable: str,
    *,
    container_name: str,
    project_root: Path,
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            inspect = subprocess.run(
                [
                    executable,
                    "container",
                    "inspect",
                    "--format",
                    "{{.State.Running}}",
                    container_name,
                ],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            inspect = None
        if (
            inspect is not None
            and inspect.returncode == 0
            and inspect.stdout.strip().lower() == "true"
        ):
            return
        time.sleep(0.1)
    raise RuntimeError("controller restart probe container did not become ready")


def run_controller_restart_acceptance(
    *,
    project_root: Path,
    state_dir: Path,
    image: str,
) -> dict[str, object]:
    executable = shutil.which("docker")
    if not executable:
        raise RuntimeError("Docker CLI is not available")

    managed_run_id = f"host-restart-{uuid4().hex}"
    job_id = f"restart-probe-{uuid4().hex}"
    queue = PersistentJobQueue(state_dir)
    queue.enqueue(
        Job(
            job_id,
            {
                "role": "controller-restart-acceptance",
                "managed_run_id": managed_run_id,
            },
            max_attempts=1,
        )
    )
    claimed = queue.claim(job_id=job_id, lease_seconds=300.0)
    if claimed is None:
        raise RuntimeError("controller restart acceptance job could not be claimed")

    container_name = docker_evaluation_container_name(job_id, claimed.attempt)
    command, cleanup = timeout_probe_command(
        image,
        container_name=container_name,
        sleep_seconds=300.0,
        docker_executable=executable,
    )
    helpers: list[subprocess.Popen[bytes]] = []
    docker_process: subprocess.Popen[bytes] | None = None

    try:
        dashboard_marker = f"moon-restart-dashboard-{managed_run_id}"
        research_marker = f"moon-restart-research-{managed_run_id}"
        helper_script = "import time; time.sleep(300)"
        dashboard = spawn_managed_process(
            [sys.executable, "-c", helper_script, dashboard_marker],
            project_root,
        )
        research = spawn_managed_process(
            [sys.executable, "-c", helper_script, research_marker],
            project_root,
        )
        helpers.extend((dashboard, research))

        first = SystemController(state_dir=state_dir, project_root=project_root)
        first._write_state(
            {
                "status": "STARTED",
                "managed_run_id": managed_run_id,
                "dashboard_port": 8080,
                "evaluation_execution": "docker_worker",
                "orders_enabled": False,
                "components": [
                    {
                        "id": "dashboard",
                        "status": "STARTED",
                        "pid": dashboard.pid,
                        "identity_markers": [dashboard_marker],
                    },
                    {
                        "id": "research_worker",
                        "status": "STARTED",
                        "pid": research.pid,
                        "identity_markers": [research_marker],
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

        docker_process = subprocess.Popen(
            command,
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_for_container_running(
            executable,
            container_name=container_name,
            project_root=project_root,
        )

        recovered = SystemController(state_dir=state_dir, project_root=project_root)
        status = recovered.status()
        if status.get("status") != "RUNNING":
            raise RuntimeError("recreated controller did not recover RUNNING state")
        if status.get("managed_run_id") != managed_run_id:
            raise RuntimeError("recreated controller lost managed_run_id")

        raw_components = status.get("components")
        if not isinstance(raw_components, list):
            raise RuntimeError("recreated controller returned invalid components")
        components = {
            item.get("id"): item
            for item in raw_components
            if isinstance(item, dict)
        }
        evaluation = components.get("evaluation_backend")
        if not isinstance(evaluation, dict) or evaluation.get("active_jobs") != 1:
            raise RuntimeError("recreated controller did not report active Docker job")

        runtime = status.get("runtime")
        runtime_evaluation = runtime.get("evaluation") if isinstance(runtime, dict) else None
        active_jobs = (
            runtime_evaluation.get("active_jobs")
            if isinstance(runtime_evaluation, dict)
            else None
        )
        if not isinstance(active_jobs, list) or not any(
            isinstance(item, dict) and item.get("job_id") == job_id
            for item in active_jobs
        ):
            raise RuntimeError("runtime snapshot did not recover active Docker job")
        if not isinstance(runtime, dict) or runtime.get("orders_enabled") is not False:
            raise RuntimeError("recovered runtime did not preserve orders_enabled=false")

        stopped = recovered.stop()
        if stopped.get("status") != "STOPPED":
            raise RuntimeError("recovered controller could not stop managed system")
        current = queue.get(job_id)
        if current.status is not JobStatus.CANCELLED:
            raise RuntimeError("recovered stop did not cancel owned Docker job")

        inspect = subprocess.run(
            [executable, "container", "inspect", container_name],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if inspect.returncode == 0:
            raise RuntimeError("recovered stop left Docker container running")

        for helper in helpers:
            try:
                helper.wait(timeout=5)
            except (AttributeError, subprocess.TimeoutExpired):
                raise RuntimeError("recovered stop left managed process running") from None

        final_status = recovered.status()
        final_runtime = final_status.get("runtime")
        if final_status.get("status") != "STOPPED":
            raise RuntimeError("controller did not persist STOPPED state")
        if (
            not isinstance(final_runtime, dict)
            or final_runtime.get("orders_enabled") is not False
        ):
            raise RuntimeError("stopped runtime did not preserve orders_enabled=false")

        return {
            "status": "PASS",
            "probe": "controller_restart",
            "managed_run_id": managed_run_id,
            "job_id": job_id,
            "queue_attempt": claimed.attempt,
            "recovered_status": status.get("status"),
            "active_jobs_after_reconnect": evaluation.get("active_jobs"),
            "stop_status": stopped.get("status"),
            "queue_status_after_stop": current.status.value,
            "container_name": container_name,
            "container_removed": True,
            "processes_stopped": True,
            "final_status": final_status.get("status"),
            "orders_enabled": False,
        }
    finally:
        try:
            subprocess.run(
                cleanup,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        for helper in helpers:
            try:
                if helper.poll() is None:
                    helper.terminate()
                    helper.wait(timeout=5)
            except (AttributeError, OSError, subprocess.TimeoutExpired):
                pass
        if docker_process is not None:
            try:
                docker_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                docker_process.terminate()
        try:
            current = queue.get(job_id)
            if current.status is JobStatus.RUNNING:
                queue.cancel_running(job_id)
            elif current.status is JobStatus.QUEUED:
                queue.cancel_queued(job_id)
        except (KeyError, ValueError):
            pass


def run_acceptance(
    *,
    project_root: Path,
    state_dir: Path,
    image: str,
    source_path: str,
    data_path: str,
    series_data_path: str | None = None,
) -> dict[str, object]:
    managed_run_id = f"host-acceptance-{uuid4().hex}"
    attempt_id = f"host-acceptance-{uuid4().hex}"
    executor = QueuedEvaluationExecutor(
        state_dir,
        project_root=project_root,
        execution_mode="docker_worker",
        docker_image=image,
        max_retries=0,
        managed_run_id=managed_run_id,
    )
    result = executor.run(
        run_local_evaluation,
        source_path=source_path,
        data_path=data_path,
        series_data_path=series_data_path,
        method="grid",
        count=1,
        seed=0,
        min_trades=0,
        min_annual_trades=0,
        min_qqq_cagr_delta=None,
        attempt_id=attempt_id,
    )
    jobs = PersistentJobQueue(state_dir).jobs_for_run(managed_run_id)
    if len(jobs) != 1:
        raise RuntimeError("single-job acceptance did not produce exactly one durable job")
    job = jobs[0]
    if job.status is not JobStatus.SUCCEEDED:
        raise RuntimeError("single-job acceptance did not persist SUCCEEDED queue state")
    research_run_id = result.get("research_run_id")
    result_attempt_id = result.get("attempt_id")
    if not isinstance(research_run_id, str) or not research_run_id:
        raise RuntimeError("single-job acceptance result lacks research_run_id")
    if not isinstance(result_attempt_id, str) or not result_attempt_id:
        raise RuntimeError("single-job acceptance result lacks attempt_id")
    evidence = verify_docker_evidence(
        state_dir=state_dir,
        research_run_id=research_run_id,
        attempt_id=result_attempt_id,
        job_id=job.job_id,
        managed_run_id=managed_run_id,
    )
    return {
        "status": "PASS",
        "evaluation_status": result.get("status", "UNKNOWN"),
        "candidate_count": result.get("candidate_count"),
        "managed_run_id": managed_run_id,
        "research_run_id": research_run_id,
        "attempt_id": result_attempt_id,
        "job_id": job.job_id,
        "queue_status": job.status.value,
        "queue_attempt": job.attempt,
        "durable_job_count": len(jobs),
        "evidence_verified": evidence["status"] == "VERIFIED",
        "evidence": evidence,
        "state_dir": str(state_dir),
        "orders_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    state_dir = (project_root / args.state_dir).resolve()
    try:
        if args.check_build_context:
            contract = worker_build_contract(args.image, project_root=project_root)
            print(
                json.dumps(
                    {
                        "status": "STATIC_READY",
                        "checks": contract,
                        "build_command": docker_build_command(
                            args.image, project_root=project_root
                        ),
                        "image_built": False,
                        "orders_enabled": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        checks = (
            build_worker_image(args.image, project_root=project_root)
            if args.build_image
            else docker_prerequisites(args.image, project_root=project_root)
        )
        if args.check_only:
            print(
                json.dumps(
                    {
                        "status": "READY",
                        "checks": checks,
                        "image_built": bool(args.build_image),
                        "orders_enabled": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.verify_timeout:
            result = run_timeout_acceptance(
                project_root=project_root,
                state_dir=state_dir,
                image=args.image,
                timeout_seconds=args.timeout_seconds,
            )
            result["checks"] = checks
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.verify_retry_exhaustion:
            result = run_retry_exhaustion_acceptance(
                project_root=project_root,
                state_dir=state_dir,
                image=args.image,
                timeout_seconds=args.timeout_seconds,
                max_retries=args.max_retries,
            )
            result["checks"] = checks
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.verify_controller_restart:
            result = run_controller_restart_acceptance(
                project_root=project_root,
                state_dir=state_dir,
                image=args.image,
            )
            result["checks"] = checks
            print(json.dumps(result, sort_keys=True))
            return 0
        source_path = args.source_path
        data_path = args.data_path
        if args.prepare_fixture:
            source_path, data_path = prepare_acceptance_fixture(
                project_root=project_root,
                state_dir=state_dir,
            )
        if not source_path or not data_path:
            parser.error(
                "--source-path and --data-path are required unless --prepare-fixture is used"
            )
        result = run_acceptance(
            project_root=project_root,
            state_dir=state_dir,
            image=args.image,
            source_path=source_path,
            data_path=data_path,
            series_data_path=args.series_data_path,
        )
        result["fixture_prepared"] = bool(args.prepare_fixture)
        result["checks"] = checks
        print(json.dumps(result, sort_keys=True))
        return 0
    except RuntimeError as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_class": type(exc).__name__,
                    "message": str(exc),
                    "orders_enabled": False,
                },
                sort_keys=True,
            )
        )
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Host-side acceptance check for the isolated Docker evaluation worker."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--state-dir", default="state/docker-acceptance")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--source-path", default="")
    parser.add_argument("--data-path", default="")
    parser.add_argument("--series-data-path", default=None)
    parser.add_argument("--prepare-fixture", action="store_true")
    parser.add_argument("--verify-timeout", action="store_true")
    parser.add_argument("--verify-retry-exhaustion", action="store_true")
    parser.add_argument("--verify-controller-restart", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=0.5)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--check-build-context", action="store_true")
    parser.add_argument("--build-image", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
