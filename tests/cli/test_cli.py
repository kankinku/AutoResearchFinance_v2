from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "cli.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_init_creates_state_and_status_returns_json(tmp_path: Path) -> None:
    initialized = run_cli("init", "--state-dir", str(tmp_path / "state"), cwd=ROOT)
    status = run_cli("status", "--state-dir", str(tmp_path / "state"), cwd=ROOT)

    assert initialized.returncode == 0
    assert status.returncode == 0
    payload = json.loads(status.stdout)
    assert payload["champion"] == "EMPTY"
    assert (tmp_path / "state" / "frontier.json").is_file()
