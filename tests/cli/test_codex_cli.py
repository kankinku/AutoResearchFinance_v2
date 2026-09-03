from __future__ import annotations

import json
import sys
from pathlib import Path

import cli
from cli import main


def test_research_intent_command_uses_codex_executable_and_records_status(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    env_path = tmp_path / ".env"
    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        "import os, sys\n"
        "from pathlib import Path\n"
        "output = Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "output.write_text(os.environ['QUANT_CODEX_TEST_OUTPUT'], encoding='utf-8')\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" "{fake_codex}"'
    env_path.write_text(
        f"QUANT_CODEX_COMMAND={command}\nQUANT_CODEX_MODEL=fixture\nQUANT_CODEX_TIMEOUT_SECONDS=30\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("QUANT_CODEX_TEST_OUTPUT", json.dumps({
        "mode": "structure",
        "parent_ids": ["champion-1"],
        "operations": [],
        "rationale": "test",
    }))

    assert main(
        [
            "research-intent",
            "--state-dir",
            str(tmp_path / "state"),
            "--env-file",
            str(env_path),
            "--project-root",
            str(tmp_path),
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "VALIDATED"


def test_autoresearch_command_dispatches_to_bounded_codex_loop(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        pass

    def fake_from_env(*args: object, **kwargs: object) -> FakeProvider:
        captured["provider_args"] = args
        captured["provider_kwargs"] = kwargs
        return FakeProvider()

    def fake_run(config: object, director: object) -> dict[str, object]:
        captured["config"] = config
        captured["director"] = director
        return {"status": "COMPLETED", "completed_generations": 2, "orders_enabled": False}

    monkeypatch.setattr(cli.CodexExecProvider, "from_env", fake_from_env)
    monkeypatch.setattr(cli, "run_autoresearch", fake_run)

    assert main(
        [
            "autoresearch",
            "--source",
            "strategy.yaml",
            "--data",
            "data.parquet",
            "--env-file",
            ".env",
            "--project-root",
            str(tmp_path),
            "--generations",
            "2",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "COMPLETED"
    config = captured["config"]
    assert config.generations == 2
    assert config.source_path == "strategy.yaml"
    assert config.min_qqq_cagr_delta == 0.10


def test_terminal_chat_command_uses_read_only_codex_chat_provider(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    captured: dict[str, object] = {}

    class FakeChat:
        @classmethod
        def from_env(cls, env_path: Path, *, workdir: Path) -> FakeChat:
            captured["env_path"] = env_path
            captured["workdir"] = workdir
            return cls()

        def ask(self, prompt: str) -> str:
            captured["prompt"] = prompt
            return "응답"

    monkeypatch.setattr(cli, "CodexChatProvider", FakeChat)

    assert main(
        [
            "terminal",
            "--mode",
            "chat",
            "--prompt",
            "현재 전략 상태를 요약해줘",
            "--env-file",
            ".env",
            "--project-root",
            str(tmp_path),
        ]
    ) == 0

    assert capsys.readouterr().out.strip() == "응답"
    assert captured["prompt"] == "현재 전략 상태를 요약해줘"
