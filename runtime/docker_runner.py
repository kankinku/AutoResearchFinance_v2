from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from runtime.lean_worker import LeanWorkerSpec, validate_worker_spec

Process = Callable[[list[str], float], tuple[int, str, str]]


@dataclass(frozen=True)
class DockerRunResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class DockerLeanRunner:
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
        self, spec: LeanWorkerSpec, worker_command: Sequence[str]
    ) -> list[str]:
        validate_worker_spec(spec)
        if not worker_command or any(not item for item in worker_command):
            raise ValueError("worker command is required")
        data_dir = str(spec.data_dir.resolve())
        output_dir = str(spec.output_dir.resolve())
        return [
            self.docker_binary,
            "run",
            "--rm",
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
            "-v",
            f"{data_dir}:/input:ro",
            "-v",
            f"{output_dir}:/output:rw",
            self.image,
            *worker_command,
        ]

    def run(
        self, spec: LeanWorkerSpec, worker_command: Sequence[str], *, timeout: float
    ) -> DockerRunResult:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        command = self.build_command(spec, worker_command)
        returncode, stdout, stderr = self._process(command, timeout)
        return DockerRunResult(tuple(command), returncode, stdout, stderr)

    @staticmethod
    def _subprocess(command: list[str], timeout: float) -> tuple[int, str, str]:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr
