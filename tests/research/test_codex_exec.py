"""Retired Codex execution is absent; GPT research needs no subprocess LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from research.llm.codex_exec import CodexExecProvider
from research.llm.gpt_context import sanitize_context


def test_no_embedded_model_provider_can_be_initialized(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="removed"):
        CodexExecProvider(workdir=tmp_path)
    with pytest.raises(RuntimeError, match="removed"):
        CodexExecProvider.from_env(tmp_path / "legacy.env", workdir=tmp_path)


def test_gpt_context_drops_sensitive_data_without_invoking_model() -> None:
    assert sanitize_context(
        {"token": "s", "raw_market_rows": [1], "sealed_oos": [2], "generation": 3}
    ) == {"generation": 3}
