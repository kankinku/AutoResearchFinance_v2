from __future__ import annotations

import datetime as dt
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.llm.director import ResearchIntent

DEFAULT_CODEX_TIMEOUT_SECONDS = 300.0


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
        model: str | None = None,
        timeout_seconds: float = DEFAULT_CODEX_TIMEOUT_SECONDS,
        service_tier: str = "fast",
        status_path: Path | None = None,
        runner: ExecRunner | None = None,
    ) -> None:
        if not executable.strip():
            raise ValueError("Codex executable is required")
        if timeout_seconds <= 0:
            raise ValueError("Codex timeout must be positive")
        if service_tier not in {"fast", "flex"}:
            raise ValueError("Codex service tier must be fast or flex")
        self.executable = executable
        self.workdir = workdir.resolve()
        self.schema_path = schema_path or _default_schema_path()
        self.model = model.strip() if model and model.strip() else None
        self.timeout_seconds = timeout_seconds
        self.service_tier = service_tier
        self.status_path = status_path
        self._runner = runner or _run_codex

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        self._write_status("RUNNING", "NONE", operation="propose")
        try:
            payload = self._propose(context)
        except Exception:
            self._write_status("OFFLINE", "FAILED", operation="propose")
            raise
        self._write_status("ONLINE", "VALIDATED", operation="propose")
        return payload

    def _propose(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._execute_request(
            {
                "instruction": (
                    "Return exactly one ResearchIntent JSON object using only the canonical "
                    "typed operation fields defined by the output schema. Never use JSON "
                    "Patch add/replace/remove operations. ADD_RULE and ADD_REGIME_FILTER "
                    "must use a condition object, SET_PARAMETER must use a scalar value, "
                    "and ADD_FEATURE must use a typed feature object. Use only the verified "
                    "condition operators cross_above, cross_below, less_than, less_equal, "
                    "greater_than, greater_equal, or equal. Use dotted paths such as "
                    "entry.conditions.<index> and indicators.<alias>; indicator changes "
                    "must carry an indicator object at indicators.<alias>. Do not edit "
                    "files, write Python, change evaluators, or access credentials."
                ),
                "context": sanitize_context(context),
            }
        )

    def repair(
        self,
        context: dict[str, Any],
        invalid_intent: dict[str, Any] | None,
        error: str,
    ) -> dict[str, Any]:
        """Use a fresh read-only Codex process to repair an invalid intent."""

        self._write_status("RUNNING", "REPAIRING", operation="repair")
        try:
            payload = self._execute_request(
                {
                    "instruction": (
                        "Act as an independent intent repair agent. Return exactly one "
                        "ResearchIntent JSON object that fixes the supplied validation error. "
                        "Use only registered feature selections and canonical typed mutation "
                        "operations with Strategy IR-root dotted paths. Never emit JSON Patch "
                        "add/replace/remove operations. Condition targets must contain a "
                        "condition object, not a boolean or list. Use only the verified "
                        "condition operators cross_above, cross_below, less_than, less_equal, "
                        "greater_than, greater_equal, or equal. Use dotted paths such as "
                        "entry.conditions.<index> and indicators.<alias>, and carry indicator "
                        "changes in the typed indicator field. Remove any unregistered feature "
                        "proposal. Do not edit files, write Python, change evaluators, access "
                        "credentials, or place orders."
                    ),
                    "context": sanitize_context(context),
                    "invalid_intent": sanitize_context(invalid_intent),
                    "repair_error": error,
                }
            )
        except Exception:
            self._write_status("OFFLINE", "FAILED", operation="repair")
            raise
        self._write_status("ONLINE", "REPAIRED", operation="repair")
        return payload

    def _execute_request(self, request: Mapping[str, object]) -> dict[str, Any]:
        self.workdir.mkdir(parents=True, exist_ok=True)
        prompt = json.dumps(request, ensure_ascii=False, sort_keys=True)
        with tempfile.TemporaryDirectory(prefix=".codex-intent-", dir=self.workdir) as directory:
            output_path = Path(directory) / "intent.json"
            executable_parts = shlex.split(self.executable, posix=True)
            if not executable_parts:
                raise ValueError("Codex executable is required")
            command = [
                *executable_parts,
                "exec",
                "-c",
                f'service_tier="{self.service_tier}"',
                "-",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(self.schema_path.resolve()),
                "-o",
                str(output_path),
            ]
            if self.model is not None:
                command[2:2] = ["-m", self.model]
            result = self._runner(
                command,
                prompt,
                self.workdir,
                _child_environment(),
                self.timeout_seconds,
            )
            if result.returncode != 0:
                raise ValueError(_execution_error(result))
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                intent = ResearchIntent.model_validate(payload)
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError("Codex returned an invalid ResearchIntent") from exc
        payload = intent.model_dump(mode="json", exclude_none=True)
        if payload.get("feature_selections") == []:
            payload.pop("feature_selections")
        return payload

    @classmethod
    def from_env(
        cls,
        env_path: Path,
        *,
        workdir: Path,
        status_path: Path | None = None,
    ) -> CodexExecProvider:
        values = _read_settings(env_path)
        executable = values.get("QUANT_CODEX_COMMAND", "codex")
        model = values.get("QUANT_CODEX_MODEL", "gpt-5.4-mini")
        try:
            timeout = float(
                values.get("QUANT_CODEX_TIMEOUT_SECONDS", str(DEFAULT_CODEX_TIMEOUT_SECONDS))
            )
        except ValueError as exc:
            raise ValueError("QUANT_CODEX_TIMEOUT_SECONDS must be numeric") from exc
        return cls(
            executable=executable,
            workdir=workdir,
            model=model,
            timeout_seconds=timeout,
            service_tier=values.get("QUANT_CODEX_SERVICE_TIER", "fast").lower(),
            status_path=status_path,
        )

    def _write_status(
        self, status: str, last_result: str, *, operation: str | None = None
    ) -> None:
        if self.status_path is not None:
            write_provider_status(
                self.status_path, "codex_exec", status, last_result, operation=operation
            )


def write_provider_status(
    path: Path,
    provider: str,
    status: str,
    last_result: str,
    *,
    operation: str | None = None,
) -> None:
    payload = {
        "provider": provider,
        "status": status,
        "last_result": last_result,
        "last_call_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if operation is not None:
        payload["operation"] = operation
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        return


def record_intent(path: Path, intent: ResearchIntent) -> None:
    payload = sanitize_context(intent.model_dump(mode="json", exclude_none=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                {"timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "intent": payload},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


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


def _read_settings(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"Codex settings file does not exist: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        raw_value = value.strip()
        values[name.strip()] = (
            raw_value
            if name.strip() == "QUANT_CODEX_COMMAND"
            else _strip_outer_quotes(raw_value)
        )
    return values


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _run_codex(
    command: list[str],
    input_text: str,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
) -> CodexExecResult:
    command = _resolve_codex_command(command, env)
    if sys.platform == "win32" and _is_windows_wrapper(command[0] if command else ""):
        return _run_codex_windows_process_tree(command, input_text, cwd, env, timeout)
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
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            return CodexExecResult(
                124,
                "",
                f"Codex execution timed out after {timeout:g} seconds",
            )
        return CodexExecResult(127, "", f"Codex process could not start: {exc}")
    return CodexExecResult(completed.returncode, completed.stdout, completed.stderr)


def _is_windows_wrapper(executable: str) -> bool:
    return executable.lower().endswith((".cmd", ".bat", ".ps1"))


def _run_codex_windows_process_tree(
    command: list[str],
    input_text: str,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
) -> CodexExecResult:
    """Run npm shims with a killable process tree on Windows."""

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        creationflags=creationflags,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_windows_process_tree(process.pid)
        process.communicate()
        return CodexExecResult(
            124,
            "",
            f"Codex execution timed out after {timeout:g} seconds; process tree terminated",
        )
    return CodexExecResult(process.returncode, stdout, stderr)


def _kill_windows_process_tree(pid: int) -> None:
    """Terminate only the process tree rooted at the Codex child we spawned."""

    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return


def _resolve_codex_command(command: list[str], env: Mapping[str, str]) -> list[str]:
    if not command or sys.platform != "win32":
        return command
    path = env.get("PATH")
    resolved = shutil.which(command[0], path=path)
    if resolved is None and not os.path.splitext(command[0])[1]:
        for suffix in (".cmd", ".exe", ".ps1"):
            resolved = shutil.which(command[0] + suffix, path=path)
            if resolved is not None:
                break
    if resolved is None:
        return command
    if resolved.lower().endswith(".ps1"):
        shell = shutil.which("pwsh", path=path) or shutil.which("powershell.exe", path=path)
        if shell is None:
            return command
        return [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved, *command[1:]]
    return [resolved, *command[1:]]


def _execution_error(result: CodexExecResult) -> str:
    diagnostic = " ".join(result.stderr.split())
    if len(diagnostic) > 1000:
        diagnostic = diagnostic[:997] + "..."
    suffix = f": {diagnostic}" if diagnostic else ""
    return f"Codex execution failed (exit {result.returncode}){suffix}"
