from __future__ import annotations

import json
import sys
from pathlib import Path

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
        f"QUANT_CODEX_COMMAND={command}\nQUANT_CODEX_TIMEOUT_SECONDS=30\n",
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
