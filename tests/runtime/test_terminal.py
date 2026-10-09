from __future__ import annotations

from pathlib import Path

import pytest

from runtime.terminal import (
    CodexChatProvider,
    DirectEditGateError,
    parse_terminal_command,
    validate_direct_edit_gate,
)


def test_terminal_parser_separates_research_mode_and_chat_prompt() -> None:
    assert parse_terminal_command("/mode autoresearch").name == "mode"
    assert parse_terminal_command("/research 12").arguments == ("12",)
    assert parse_terminal_command("Mimir /research 12").name == "research"
    assert parse_terminal_command("Mimir /research 12").arguments == ("12",)
    command = parse_terminal_command("QQQ 전략의 최근 평가를 요약해줘")
    assert command.name == "chat"
    assert command.arguments == ("QQQ 전략의 최근 평가를 요약해줘",)


def test_terminal_parser_rejects_unbounded_research() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        parse_terminal_command("/research 0")
    with pytest.raises(ValueError, match="positive integer"):
        parse_terminal_command("/research forever")


def test_direct_edit_requires_confirmation_and_disposable_worktree(tmp_path: Path) -> None:
    with pytest.raises(DirectEditGateError, match="confirmation"):
        validate_direct_edit_gate(
            mode="direct-edit",
            confirmed=False,
            worktree=tmp_path,
            project_root=tmp_path.parent,
        )

    with pytest.raises(DirectEditGateError, match="separate"):
        validate_direct_edit_gate(
            mode="direct-edit",
            confirmed=True,
            worktree=tmp_path.parent,
            project_root=tmp_path.parent,
        )

    validate_direct_edit_gate(
        mode="direct-edit",
        confirmed=True,
        worktree=tmp_path,
        project_root=tmp_path.parent,
    )


def test_retired_terminal_chat_cannot_run_codex(tmp_path: Path) -> None:
    provider = CodexChatProvider(workdir=tmp_path)
    with pytest.raises(RuntimeError, match="removed"):
        provider.ask("요약")
