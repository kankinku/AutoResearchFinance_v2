"""D2: fork-local MCP surfaces, exact academic schema and direct STDIO parity."""

import asyncio
from pathlib import Path

import pytest

from integrations.chatgpt_mcp_sdk import chatgpt_tools
from integrations.codex_mcp_core import _tools
from integrations.python_mcp_direct import (
    QuantMCPDirectClient,
    QuantMCPSettings,
    ReadOnlyToolRejected,
)


def test_mcp_surface_difference_is_explicit():
    codex_names = {t["name"] for t in _tools()}
    chatgpt_names = {t["name"] for t in chatgpt_tools()}
    assert len(codex_names) == 13
    assert len(chatgpt_names) == 32
    assert "submit_algorithm_plan" not in codex_names
    assert "submit_algorithm_plan" in chatgpt_names
    assert "get_algorithm_research" in chatgpt_names


def test_chatgpt_public_schema_exposes_service_preflight_flags():
    schema = next(
        t["inputSchema"] for t in chatgpt_tools()
        if t["name"] == "submit_algorithm_plan"
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["require_execution_change"]["type"] == "boolean"
    assert schema["properties"]["require_trade_activity"]["type"] == "boolean"
    assert schema["properties"]["require_trade_activity"]["default"] is False


def test_codecs_cannot_fake_academic_endpoint_by_allowlist(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    sid = "b" * 32
    codex = QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            scope_session=sid,
            surface="codex",
        )
    )
    with pytest.raises(ReadOnlyToolRejected, match="ChatGPT academic MCP surface"):
        codex.require_read_only_tool("get_algorithm_research")
    assert codex._server_params().args[1] == "integrations.codex_mcp_server"

    chatgpt = QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            scope_session=sid,
            surface="chatgpt_academic",
        )
    )
    chatgpt.require_read_only_tool("get_algorithm_research")
    assert chatgpt._server_params().args[1] == "integrations.chatgpt_mcp_stdio"
    with pytest.raises(ValueError, match="session mismatch"):
        chatgpt.assert_session("a" * 32)


def test_invalid_mcp_surface_rejected(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    with pytest.raises(ValueError, match="invalid MCP surface"):
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            surface="any-untrusted-mcp",
        )


def test_scoped_session_read_requires_academic_surface(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    client = QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            surface="chatgpt_academic",
        )
    )
    with pytest.raises(ReadOnlyToolRejected):
        client.require_read_only_tool("get_algorithm_research")


def test_chatgpt_academic_real_stdio_probe_is_read_only(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    client = QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            surface="chatgpt_academic",
        )
    )
    report = asyncio.run(client.probe())
    assert report["mcp_tool_count"] == 32
    assert report["orders_enabled"] is False
    assert report["model_calls"] == 0
    assert report["quant_status"] == "NOT_INITIALIZED"


def test_academic_checkpoint_view_rejects_wrong_scope_before_process_start(tmp_path: Path):

    root = tmp_path / "fork"
    root.mkdir()
    client = QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            scope_session="c" * 32, surface="chatgpt_academic",
        )
    )
    with pytest.raises(ValueError, match="session mismatch"):
        asyncio.run(client.read_academic_checkpoint("d" * 32))


def test_academic_checkpoint_view_missing_session_does_not_modify_generation(tmp_path: Path):
    from integrations.python_mcp_direct import QuantMCPResponseError

    root = tmp_path / "fork"
    root.mkdir()
    client = QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            scope_session="c" * 32, surface="chatgpt_academic",
        )
    )
    with pytest.raises(QuantMCPResponseError):
        asyncio.run(client.read_academic_checkpoint("c" * 32))
    journal = root / "state" / "python-mcp" / "academic-gpt-checkpoints" / "cycles.sqlite"
    assert not journal.exists()
