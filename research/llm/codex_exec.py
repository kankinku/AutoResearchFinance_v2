from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.llm.director import ResearchIntent


@dataclass(frozen=True)
class CodexExecResult:
    returncode: int
    stdout: str
    stderr: str


ExecRunner = Callable[[list[str], str, Path, dict[str, str], float], CodexExecResult]


class CodexExecProvider:
    """Run Codex locally and accept only a validated ResearchIntent object."""

    def __init__(
        self,
        *,
        executable: str = "codex",
        workdir: Path,
        schema_path: Path | None = None,
        timeout_seconds: float = 120.0,
        runner: ExecRunner | None = None,
    ) -> None:
        if not executable.strip():
            raise ValueError("Codex executable is required")
        if timeout_seconds <= 0:
            raise ValueError("Codex timeout must be positive")
        self.executable = executable
        self.workdir = workdir.resolve()
        self.schema_path = schema_path or _default_schema_path()
        self.timeout_seconds = timeout_seconds
        self._runner = runner or _run_codex

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        self.workdir.mkdir(parents=True, exist_ok=True)
        sanitized = sanitize_context(context)
        prompt = json.dumps(
            {
                "instruction": (
                    "Return exactly one ResearchIntent JSON object. Do not edit files, "
                    "write Python, change evaluators, or access credentials."
                ),
                "context": sanitized,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        with tempfile.TemporaryDirectory(prefix=".codex-intent-", dir=self.workdir) as directory:
            output_path = Path(directory) / "intent.json"
            command = [
                self.executable,
                "exec",
                "-",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(self.schema_path.resolve()),
                "-o",
                str(output_path),
            ]
            result = self._runner(
                command,
                prompt,
                self.workdir,
                _child_environment(),
                self.timeout_seconds,
            )
            if result.returncode != 0:
                raise ValueError("Codex execution failed")
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                intent = ResearchIntent.model_validate(payload)
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("Codex returned an invalid ResearchIntent") from exc
        return intent.model_dump(mode="json", exclude_none=True)


def sanitize_context(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_context(item)
            for key, item in value.items()
            if not _sensitive_key(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_context(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    blocked = (
        "secret",
        "token",
        "password",
        "credential",
        "api_key",
        "authorization",
        "raw_market",
        "sealed_oos",
    )
    return any(item in normalized for item in blocked) or normalized.startswith("kis_")


def _child_environment() -> dict[str, str]:
    blocked = {"OPENAI_API_KEY", "CODEX_API_KEY", "QUANT_LLM_API_KEY"}
    return {
        key: value
        for key, value in os.environ.items()
        if key not in blocked and not key.startswith("KIS_")
    }


def _default_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas" / "research_intent.schema.json"


def _run_codex(
    command: list[str],
    input_text: str,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
) -> CodexExecResult:
    try:
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        del exc
        return CodexExecResult(1, "", "")
    return CodexExecResult(completed.returncode, completed.stdout, completed.stderr)
