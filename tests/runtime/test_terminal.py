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


def test_codex_chat_provider_uses_read_only_exec_without_sensitive_environment(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def runner(command: list[str], prompt: str, cwd: Path, env: dict[str, str], timeout: float):
        captured.update(command=command, prompt=prompt, cwd=cwd, env=env, timeout=timeout)
        return 0, "Codex response"

    provider = CodexChatProvider(
        executable="codex",
        workdir=tmp_path,
        runner=runner,
    )

    assert provider.ask("요약") == "Codex response"
    assert captured["command"][:4] == ["codex", "exec", "-", "--ephemeral"]
    assert "--sandbox" in captured["command"]
    env = captured["env"]
    assert isinstance(env, dict)
    assert "OPENAI_API_KEY" not in env
    assert not any(key.startswith("KIS_") for key in env)
