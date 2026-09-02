from __future__ import annotations

from pathlib import Path

from research.llm.codex_exec import CodexExecProvider


def test_codex_provider_loads_non_secret_runtime_settings(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "QUANT_CODEX_COMMAND=codex",
                "QUANT_CODEX_TIMEOUT_SECONDS=45",
                "KIS_PAPER_APP_SECRET=must-not-be-read-as-codex-setting",
            ]
        ),
        encoding="utf-8",
    )

    provider = CodexExecProvider.from_env(
        env_path,
        workdir=tmp_path,
        status_path=tmp_path / "status.json",
    )

    assert provider.executable == "codex"
    assert provider.model == "gpt-5.4-mini"
    assert provider.timeout_seconds == 45.0
