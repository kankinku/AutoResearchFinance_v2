from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client

from integrations.codex_mcp_server import (
    _PUBLIC_TOOL_PLANES,
    CodexMCPServer,
    _all_tools,
    _tools,
    _with_public_contract,
    create_mcp_server,
)

ROOT = Path(__file__).resolve().parents[2]


async def _initialize(module: str, state_dir: Path) -> types.InitializeResult:
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            module,
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(ROOT),
        ],
        cwd=ROOT,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            client_info=types.Implementation(name="phase5-cutover-test", version="1"),
        ) as session:
            return await session.initialize()


def test_phase5_5_canonical_entrypoint_negotiates_through_official_sdk(
    tmp_path: Path,
) -> None:
    result = asyncio.run(
        _initialize(
            "integrations.codex_mcp_server",
            tmp_path / "canonical",
        )
    )

    assert result.protocol_version == "2025-11-25"
    assert result.server_info.name == "quant-autoresearch"
    assert result.capabilities.tools is not None


def test_phase5_5_manual_rollback_entrypoint_preserves_legacy_transport(
    tmp_path: Path,
) -> None:
    result = asyncio.run(
        _initialize(
            "integrations.codex_mcp_manual_server",
            tmp_path / "manual",
        )
    )

    assert result.protocol_version == "2024-11-05"
    assert result.server_info.name == "quant-autoresearch"


def test_phase5_5_canonical_module_preserves_python_import_contract(tmp_path: Path) -> None:
    server = create_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    assert isinstance(server, CodexMCPServer)
    assert len(_tools()) == 13
    assert len(_all_tools()) == 18
    assert len(_PUBLIC_TOOL_PLANES) == 13

    payload = _with_public_contract(
        "get_system_status",
        {"status": "STOPPED"},
    )
    assert isinstance(payload, dict)
    assert payload["_contract"]["orders_enabled"] is False
