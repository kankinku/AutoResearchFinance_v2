from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from orchestration.evaluation_runner import run_local_evaluation
from runtime.evaluation_executor import QueuedEvaluationExecutor

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


def run_acceptance(
    *,
    project_root: Path,
    state_dir: Path,
    image: str,
    source_path: str,
    data_path: str,
    series_data_path: str | None = None,
) -> dict[str, object]:
    executor = QueuedEvaluationExecutor(
        state_dir,
        project_root=project_root,
        execution_mode="docker_worker",
        docker_image=image,
        max_retries=0,
        managed_run_id=f"host-acceptance-{uuid4().hex}",
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
        attempt_id=f"host-acceptance-{uuid4().hex}",
    )
    return {
        "status": "PASS",
        "evaluation_status": result.get("status", "UNKNOWN"),
        "candidate_count": result.get("candidate_count"),
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
        if not args.source_path or not args.data_path:
            parser.error("--source-path and --data-path are required unless --check-only is used")
        result = run_acceptance(
            project_root=project_root,
            state_dir=state_dir,
            image=args.image,
            source_path=args.source_path,
            data_path=args.data_path,
            series_data_path=args.series_data_path,
        )
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
    parser.add_argument("--check-build-context", action="store_true")
    parser.add_argument("--build-image", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
