"""Independent Python->Quant MCP executor: no GPT or original P5 mutation."""

import asyncio
from pathlib import Path

import pytest

from integrations.python_mcp_direct import (
    QuantMCPDirectClient,
    QuantMCPSettings,
    ReadOnlyToolRejected,
)


def test_state_must_be_inside_its_own_project(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    with pytest.raises(ValueError, match="inside the project's state/ directory"):
        QuantMCPSettings(project_root=root, state_dir=tmp_path / "another" / "state")


def test_cross_project_p5_state_cannot_be_used(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    legacy = Path("/shared/moon-workspace/AutoResearchFinance_v2-p5-gpt-100-20261024")
    with pytest.raises(ValueError, match="inside the project's state/ directory"):
        QuantMCPSettings(project_root=root, state_dir=legacy)


def test_invalid_session_id_rejected(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    with pytest.raises(ValueError, match="32 lowercase hex"):
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            scope_session="not-a-session",
        )


def test_no_mutating_tool_available_from_read_only_client(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    client = QuantMCPDirectClient(
        QuantMCPSettings(project_root=root, state_dir=root / "state" / "python-mcp")
    )
    for name in (
        "submit_algorithm_plan", "submit_algorithm_diagnosis",
        "start_research_batch", "download_market_data", "start_system",
    ):
        with pytest.raises(ReadOnlyToolRejected):
            client.require_read_only_tool(name)
    for name in ("get_workspace_status", "list_features"):
        client.require_read_only_tool(name)
    with pytest.raises(ReadOnlyToolRejected):
        client.require_read_only_tool("get_algorithm_research")


def test_exact_session_read_scope(tmp_path: Path):
    root = tmp_path / "fork"
    root.mkdir()
    sid = "a" * 32
    client = QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root, state_dir=root / "state" / "python-mcp",
            scope_session=sid, surface="chatgpt_academic",
        )
    )
    assert client.require_read_only_tool("get_algorithm_research") is None
    with pytest.raises(ValueError, match="session mismatch"):
        client.assert_session("b" * 32)


def test_real_offline_python_mcp_stdio_probe(tmp_path: Path):
    """Real MCP subprocess, no Codex, no external API and no strategy orders."""
    root = tmp_path / "isolated-quant"
    root.mkdir()
    settings = QuantMCPSettings(
        project_root=root,
        state_dir=root / "state" / "python-mcp",
    )
    result = asyncio.run(QuantMCPDirectClient(settings).probe())
    assert result["transport"] == "stdio"
    assert result["model_calls"] == 0
    assert result["orders_enabled"] is False
    assert result["mcp_tool_count"] >= 10
    assert result["quant_status"] in {
        "PARTIAL", "READY", "MISSING", "UNINITIALIZED", "NOT_INITIALIZED",
    }
    assert result["feature_count"] >= 1
