from __future__ import annotations

from pathlib import Path

from integrations import codex_mcp_core
from integrations.codex_mcp_manual_adapter import (
    ManualCodexMCPServer,
    create_manual_mcp_server,
)
from integrations.codex_mcp_server import CodexMCPServer, create_mcp_server

ROOT = Path(__file__).resolve().parents[2]


def test_phase6_3_core_has_no_manual_jsonrpc_ownership() -> None:
    source = (ROOT / "integrations" / "codex_mcp_core.py").read_text(encoding="utf-8")

    assert "codex_mcp_protocol" not in source
    assert "def handle(" not in source
    assert "def _call(" not in source
    assert "def _tool_error(" not in source
    assert not hasattr(codex_mcp_core.CodexMCPServer, "handle")


def test_phase6_3_manual_adapter_owns_legacy_jsonrpc(tmp_path: Path) -> None:
    server = create_manual_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    assert isinstance(server, ManualCodexMCPServer)
    assert isinstance(server, codex_mcp_core.CodexMCPServer)

    initialize = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "phase6-test", "version": "1"},
            },
        }
    )
    assert initialize is not None
    assert initialize["result"]["protocolVersion"] == "2024-11-05"

    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed is not None
    assert len(listed["result"]["tools"]) == 13


def test_phase6_3_canonical_python_import_shim_preserves_legacy_test_api(
    tmp_path: Path,
) -> None:
    server = create_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    assert CodexMCPServer is ManualCodexMCPServer
    assert isinstance(server, ManualCodexMCPServer)
    assert callable(server.handle)
