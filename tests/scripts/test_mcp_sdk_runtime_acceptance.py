from __future__ import annotations

import json
import sys
from pathlib import Path

import scripts.verify_mcp_sdk_runtime as acceptance


def test_real_sdk_stdio_shadow_acceptance(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]

    result = acceptance.run_acceptance(
        project_root=repo_root,
        state_dir=tmp_path / "state",
        python_executable=sys.executable,
        timeout=30.0,
    )

    assert result == {
        "status": "PASS",
        "sdk_protocol_version": "2025-11-25",
        "legacy_protocol_version": "2024-11-05",
        "server_name": "quant-autoresearch",
        "tool_count": 13,
        "public_contract_schema_version": 1,
        "legacy_compatibility_count": 5,
        "system_status": "STOPPED",
        "canonical_entrypoint": "manual",
        "orders_enabled": False,
    }


def test_sdk_stdio_shadow_acceptance_cli_prints_safe_summary(
    tmp_path: Path,
    capsys,
) -> None:
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
    assert payload["sdk_protocol_version"] == "2025-11-25"
    assert payload["legacy_protocol_version"] == "2024-11-05"
    assert payload["tool_count"] == 13
    assert payload["legacy_compatibility_count"] == 5
    assert payload["canonical_entrypoint"] == "manual"
    assert payload["orders_enabled"] is False
    assert "content" not in payload


def test_sdk_stdio_shadow_acceptance_failure_is_sanitized(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    secret = "SECRET_SDK_STDIO_DETAIL"

    def fail(**_kwargs: object) -> dict[str, object]:
        raise RuntimeError(secret)

    monkeypatch.setattr(acceptance, "run_acceptance", fail)

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
    assert secret not in output
    payload = json.loads(output)
    assert payload == {
        "status": "BLOCKED",
        "error_class": "RuntimeError",
        "message": "SDK MCP acceptance failed",
        "orders_enabled": False,
    }
