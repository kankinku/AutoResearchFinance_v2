"""Moon's stable Funnel receives an additive Quant route, never an /mcp replacement."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_moon_quant_route_is_additive_and_local_only() -> None:
    route = (ROOT / "deployment/moon/20-quant-autoresearch.conf").read_text()
    assert "location = /quant/mcp" in route
    assert "location ^~ /quant/" in route
    assert "location = /.well-known/oauth-protected-resource/quant/mcp" in route
    assert "location = /.well-known/oauth-authorization-server/quant" in route
    assert "proxy_pass http://127.0.0.1:8787/mcp/;" in route
    assert "location = /mcp" not in route
    assert "0.0.0.0:8787" not in route


def test_quant_launcher_does_not_reuse_moon_oauth_approval_key() -> None:
    script = (ROOT / "scripts/run_quant_moon_http.sh").read_text()
    assert "state/moon-http" in script
    assert "openssl rand -hex 32" in script
    assert "chmod 600" in script
    assert "--host 127.0.0.1 --port 8787" in script
    assert "--approval-key-file" in script
    assert "MCP_OAUTH_APPROVAL_KEY" not in script
    assert "project-moon-oauth-state" not in script
    assert "QUANT_MCP_PUBLIC_BASE" in script


def test_quant_runtime_secrets_are_git_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text()
    assert "state/moon-http/" in ignore
    assert "state/tools/" in ignore
    supervisor = (ROOT / "deployment/moon/quant-mcp.supervisor.conf").read_text()
    assert "[program:quant-mcp]" in supervisor
    assert "autorestart=true" in supervisor
    assert "scripts/run_quant_moon_http.sh" in supervisor


def test_quant_launcher_runtime_pin_matches_checked_out_code() -> None:
    """Fail closed if installed runtime branch advances beyond launcher pin."""
    script = (ROOT / "scripts/run_quant_moon_http.sh").read_text()
    source_root_value = script.split('SOURCE_ROOT="', 1)[1].split('"', 1)[0]
    expected_sha = script.split('EXPECTED_SOURCE_SHA="', 1)[1].split('"', 1)[0]
    assert len(expected_sha) == 40
    assert '[[ "$(git -C "$SOURCE_ROOT" rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA" ]]' in script
    source_root = Path(source_root_value)
    if not source_root.is_dir():
        pytest.skip("Pinned Moon runtime checkout is absent in this environment")
    actual_sha = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert actual_sha == expected_sha
