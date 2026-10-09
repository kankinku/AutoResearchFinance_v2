"""The tunnel preflight can run locally without credentials or side effects."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tunnel_preflight_redacts_all_identifiers_without_network() -> None:
    key = "secret_do_not_print_" + "x" * 40
    identifier = "tunnel_DO_NOT_PRINT_123"
    result = subprocess.run(
        ["bash", "scripts/check_chatgpt_tunnel_environment.sh", "--offline"],
        cwd=ROOT,
        env={**os.environ, "CONTROL_PLANE_API_KEY": key, "QUANT_TUNNEL_ID": identifier},
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )
    assert "MCP_STDIO=READY" in result.stdout
    assert "CONTROL_PLANE_API_KEY=PRESENT" in result.stdout
    assert "QUANT_TUNNEL_ID=PRESENT" in result.stdout
    assert key not in result.stdout + result.stderr
    assert identifier not in result.stdout + result.stderr
