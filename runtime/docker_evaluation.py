from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Process = Callable[[list[str], float, list[str]], tuple[int, str, str]]


class DockerWorkerTimeout(TimeoutError):
    """Raised after a timed out worker container has been forcibly removed."""


@dataclass(frozen=True)
class DockerEvaluationResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    container_name: str


class DockerEvaluationRunner:
    """Launch one isolated evaluation-job worker container."""

    def __init__(
        self,
        *,
        image: str,
        docker_binary: str = "docker",
        process: Process | None = None,
    ) -> None:
        if not image or any(char.isspace() for char in image):
            raise ValueError("docker image must be a non-empty reference without whitespace")
        self.image = image
        self.docker_binary = docker_binary
        self._process = process or self._subprocess

    def build_command(
        self,
        *,
        project_root: Path,
        state_dir: Path,
        job_id: str,
        queue_attempt: int,
        lease_seconds: float,
    ) -> tuple[list[str], list[str], str]:
        if not job_id:
            raise ValueError("job_id is required")
        if queue_attempt < 1:
            raise ValueError("queue_attempt must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        project = project_root.resolve()
        state = state_dir.resolve()
        container_name = docker_evaluation_container_name(job_id, queue_attempt)
        command = [
            self.docker_binary,
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
            "256",
            "--memory",
            "2g",
            "--cpus",
            "1.0",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--mount",
            f"type=bind,source={project},target=/workspace,readonly",
            "--mount",
            f"type=bind,source={state},target=/workspace/state",
            "--workdir",
            "/workspace",
            self.image,
            "--role",
            "evaluation-job",
            "--state-dir",
            "/workspace/state",
            "--project-root",
            "/workspace",
            "--job-id",
            job_id,
            "--lease-seconds",
            str(lease_seconds),
        ]
        cleanup = [self.docker_binary, "rm", "-f", container_name]
        return command, cleanup, container_name

    def run(
        self,
        *,
        project_root: Path,
        state_dir: Path,
        job_id: str,
        queue_attempt: int,
        lease_seconds: float,
        timeout: float,
    ) -> DockerEvaluationResult:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        command, cleanup, container_name = self.build_command(
            project_root=project_root,
            state_dir=state_dir,
            job_id=job_id,
            queue_attempt=queue_attempt,
            lease_seconds=lease_seconds,
        )
        returncode, stdout, stderr = self._process(command, timeout, cleanup)
        return DockerEvaluationResult(
            tuple(command),
            returncode,
            stdout,
            stderr,
            container_name,
        )

    @staticmethod
    def _subprocess(
        command: list[str],
        timeout: float,
        cleanup_command: list[str],
    ) -> tuple[int, str, str]:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            try:
                subprocess.run(
                    cleanup_command,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            finally:
                try:
                    process.kill()
                except OSError:
                    pass
                process.communicate()
            raise DockerWorkerTimeout("docker evaluation worker timed out") from exc
        return process.returncode, stdout, stderr


def docker_evaluation_container_name(job_id: str, queue_attempt: int) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", job_id).strip("-.").lower()
    safe = safe[:42] or f"job-{os.getpid()}"
    return f"quant-eval-{safe}-{queue_attempt}"
