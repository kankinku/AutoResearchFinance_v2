from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path


class DirectEditGateError(ValueError):
    """Raised when the explicit direct-edit safety gate is not satisfied."""


@dataclass(frozen=True)
class TerminalCommand:
    name: str
    arguments: tuple[str, ...] = ()


class CodexChatProvider:
    """Retired compatibility class: no executable chat runtime exists."""

    def __init__(self, *, workdir: Path, **_kwargs: object) -> None:
        self.workdir = workdir.resolve()

    @classmethod
    def from_env(cls, _env_path: Path, *, workdir: Path) -> CodexChatProvider:
        raise RuntimeError("Local Codex was removed; use ChatGPT MCP")

    def ask(self, _prompt: str) -> str:
        raise RuntimeError("Local Codex was removed; use ChatGPT MCP")


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
