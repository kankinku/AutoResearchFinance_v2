"""Deprecated import compatibility only. Embedded model execution is REMOVED.

No subprocess, API calls, Codex executable, or provider implementation is present.
New research workflows use the connected ChatGPT MCP and gpt_context helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.llm.gpt_context import record_intent, sanitize_context, write_provider_status


@dataclass(frozen=True)
class CodexExecResult:
    """Historical compatibility type; no executable provider remains."""

    returncode: int
    stdout: str
    stderr: str


class CodexExecProvider:
    """Retired. Intentionally cannot be instantiated or invoke another model."""

    def __init__(self, **_kwargs: Any) -> None:
        raise RuntimeError("Embedded Codex is removed. Use the authenticated GPT MCP.")

    @classmethod
    def from_env(cls, *_args: Any, **_kwargs: Any) -> CodexExecProvider:
        raise RuntimeError("Embedded Codex is removed. Use the authenticated GPT MCP.")

    def propose(self, _context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Embedded Codex is removed")

    def repair(
        self,
        _context: dict[str, Any],
        _invalid_intent: dict[str, Any] | None,
        _error: str,
    ) -> dict[str, Any]:
        raise RuntimeError("Embedded Codex is removed")


def _read_settings(path: Path) -> dict[str, str]:
    """Read old settings for an explicit deprecation diagnostic; never run them."""
    if not path.is_file():
        raise ValueError("settings file does not exist")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _child_environment() -> dict[str, str]:
    """Compatibility only. No child LLM process is ever created."""
    return {}


__all__ = [
    "CodexExecProvider",
    "CodexExecResult",
    "record_intent",
    "sanitize_context",
    "write_provider_status",
]
