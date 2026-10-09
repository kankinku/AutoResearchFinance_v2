"""Historical Codex configuration cannot re-enable the removed executor."""

from __future__ import annotations

from pathlib import Path

import pytest

from research.llm.codex_exec import CodexExecProvider


def test_old_config_cannot_reactivate_local_codex(tmp_path: Path) -> None:
    settings = tmp_path / ".env"
    settings.write_text("QUANT_CODEX_COMMAND=codex\nQUANT_CODEX_MODEL=unused\n")
    with pytest.raises(RuntimeError, match="removed"):
        CodexExecProvider.from_env(settings, workdir=tmp_path)
