from __future__ import annotations

import json
import sys
from pathlib import Path

import scripts.verify_mcp_runtime as acceptance


def test_real_mcp_stdio_subprocess_acceptance(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]

    result = acceptance.run_acceptance(
        project_root=repo_root,
        state_dir=tmp_path / "state",
        python_executable=sys.executable,
        timeout=30,
    )

    assert result == {
        "status": "PASS",
        "protocol_version": "2024-11-05",
        "server_name": "quant-autoresearch",
        "tool_count": 10,
        "system_status": "STOPPED",
        "orders_enabled": False,
    }


def test_mcp_acceptance_cli_prints_safe_summary(tmp_path: Path, capsys) -> None:
    repo_root = Path(__file__).resolve().parents[2]

    exit_code = acceptance.main(
        [
            "--project-root",
            str(repo_root),
            "--state-dir",
            str(tmp_path / "state"),
            "--python",
            sys.executable,
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["tool_count"] == 10
    assert payload["orders_enabled"] is False
    assert "content" not in payload


def test_mcp_acceptance_failure_does_not_echo_subprocess_details(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    class Failed:
        returncode = 2
        stdout = ""
        stderr = "SECRET_PROVIDER_DETAIL"

    monkeypatch.setattr(
        acceptance.subprocess,
        "run",
        lambda *args, **kwargs: Failed(),
    )

    exit_code = acceptance.main(
        [
            "--project-root",
            str(tmp_path),
            "--state-dir",
            str(tmp_path / "state"),
        ]
    )

    assert exit_code == 2
    output = capsys.readouterr().out
    assert "SECRET_PROVIDER_DETAIL" not in output
    payload = json.loads(output)
    assert payload["status"] == "BLOCKED"
    assert payload["orders_enabled"] is False
