from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from research.llm.codex_exec import _child_environment, _read_settings


class DirectEditGateError(ValueError):
    """Raised when the explicit direct-edit safety gate is not satisfied."""


@dataclass(frozen=True)
class TerminalCommand:
    name: str
    arguments: tuple[str, ...] = ()


ChatRunner = Callable[[list[str], str, Path, dict[str, str], float], tuple[int, str]]


class CodexChatProvider:
    """Run a read-only Codex exec for ordinary terminal questions."""

    def __init__(
        self,
        *,
        executable: str = "codex",
        workdir: Path,
        model: str | None = None,
        timeout_seconds: float = 120.0,
        runner: ChatRunner | None = None,
    ) -> None:
        if not executable.strip():
            raise ValueError("Codex executable is required")
        if timeout_seconds <= 0:
            raise ValueError("Codex timeout must be positive")
        self.executable = executable
        self.workdir = workdir.resolve()
        self.model = model.strip() if model and model.strip() else None
        self.timeout_seconds = timeout_seconds
        self._runner = runner or _run_chat

    @classmethod
    def from_env(cls, env_path: Path, *, workdir: Path) -> CodexChatProvider:
        values = _read_settings(env_path)
        try:
            timeout = float(values.get("QUANT_CODEX_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise ValueError("QUANT_CODEX_TIMEOUT_SECONDS must be numeric") from exc
        return cls(
            executable=values.get("QUANT_CODEX_COMMAND", "codex"),
            workdir=workdir,
            model=values.get("QUANT_CODEX_MODEL"),
            timeout_seconds=timeout,
        )

    def ask(self, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("chat prompt cannot be empty")
        command = [
            *shlex.split(self.executable, posix=True),
            "exec",
            "-",
            "--ephemeral",
            "--sandbox",
            "read-only",
        ]
        if self.model is not None:
            command[2:2] = ["-m", self.model]
        returncode, output = self._runner(
            command, prompt, self.workdir, _child_environment(), self.timeout_seconds
        )
        if returncode != 0:
            raise ValueError("Codex chat execution failed")
        return output.strip()


def _run_chat(
    command: list[str],
    prompt: str,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return result.returncode, result.stdout


_COMMANDS = frozenset({"mode", "research", "repeat", "backtest", "status", "stop", "help", "exit"})


def parse_terminal_command(line: str) -> TerminalCommand:
    text = line.strip()
    if not text:
        raise ValueError("terminal command cannot be empty")
    words = text.split(maxsplit=1)
    if words[0].casefold() == "mimir":
        if len(words) == 1:
            raise ValueError("Mimir command is required after the Mimir prefix")
        text = words[1].strip()
    if not text.startswith("/"):
        return TerminalCommand("chat", (text,))
    try:
        tokens = shlex.split(text[1:])
    except ValueError as exc:
        raise ValueError("terminal command quoting is invalid") from exc
    if not tokens or tokens[0].lower() not in _COMMANDS:
        raise ValueError(f"unknown terminal command: {tokens[0] if tokens else ''}")
    name = tokens[0].lower()
    arguments = tuple(tokens[1:])
    if name == "mode":
        if len(arguments) != 1 or arguments[0] not in {"chat", "autoresearch", "direct-edit"}:
            raise ValueError("mode must be chat, autoresearch, or direct-edit")
    elif name in {"research", "repeat"}:
        if len(arguments) != 1 or not arguments[0].isdigit() or int(arguments[0]) <= 0:
            raise ValueError(f"{name} requires a positive integer")
    elif name in {"backtest", "status", "stop", "help", "exit"} and arguments:
        raise ValueError(f"{name} does not accept arguments")
    return TerminalCommand(name, arguments)


def validate_direct_edit_gate(
    *, mode: str, confirmed: bool, worktree: Path | None, project_root: Path
) -> None:
    if mode != "direct-edit":
        return
    if not confirmed:
        raise DirectEditGateError("direct-edit confirmation is required")
    if worktree is None:
        raise DirectEditGateError("direct-edit disposable worktree is required")
    resolved_worktree = worktree.resolve()
    resolved_root = project_root.resolve()
    if not resolved_worktree.is_dir():
        raise DirectEditGateError("direct-edit worktree must be an existing directory")
    if resolved_worktree == resolved_root:
        raise DirectEditGateError("direct-edit worktree must be separate from project root")


def terminal_help() -> str:
    return (
        "/mode chat|autoresearch|direct-edit\n"
        "/research <positive generations>\n"
        "/repeat <positive count>\n"
        "/backtest\n/status\n/stop\n/help\n/exit\n"
        "일반 문장은 Codex chat 질의로 전달됩니다. 연구는 유한 세대·Paper-only로 실행됩니다."
    )
