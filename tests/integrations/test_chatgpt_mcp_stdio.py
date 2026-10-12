"""The GPT-specific process entrypoint can be reached by an outbound-only tunnel."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent

ROOT = Path(__file__).resolve().parents[2]


def test_chatgpt_stdio_official_sdk_handshake_and_read_only_tool(tmp_path: Path) -> None:
    """Subprocess acceptance proves real framing and isolation from legacy SDK."""

    async def check() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "integrations.chatgpt_mcp_stdio",
                "--project-root",
                str(ROOT),
                "--state-dir",
                str(tmp_path / "state"),
            ],
            cwd=ROOT,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init = await session.initialize()
                assert init.server_info.name == "quant-autoresearch"
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert len(names) == 21
                assert "run_research_step" in names
                assert "start_system" not in names
                response = await session.call_tool("get_research_brief", {})
                assert response.is_error is not True
                assert isinstance(response.content[0], TextContent)
                result = json.loads(response.content[0].text)
                assert result["_contract"]["orders_enabled"] is False
                assert result["llm_controller"] == "external_mcp_client"

    asyncio.run(check())


def test_chatgpt_stdio_can_execute_one_development_step_and_read_evidence(tmp_path: Path) -> None:
    """Exercise real MCP tool discovery -> research execution -> immutable Evidence."""
    from memory.evidence_store import EvidenceStore
    from tests.orchestration.test_evaluation_runner import _write_inputs

    _write_inputs(tmp_path)

    async def check() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "integrations.chatgpt_mcp_stdio",
                "--project-root",
                str(tmp_path),
                "--state-dir",
                str(tmp_path / "state"),
            ],
            cwd=ROOT,
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tool_result = await session.call_tool(
                    "run_research_step",
                    {
                        "source_path": "strategy.yaml",
                        "data_path": "bars.parquet",
                        "intent": {
                            "mode": "structure",
                            "parent_ids": ["runner-test"],
                            "operations": [],
                            "rationale": "One authorized GPT-directed development baseline",
                        },
                        "method": "random",
                        "count": 1,
                        "seed": 4,
                        "min_trades": 0,
                        "min_annual_trades": 0,
                        "min_qqq_cagr_delta": 0.0,
                    },
                )
                assert tool_result.is_error is not True
                assert isinstance(tool_result.content[0], TextContent)
                result = json.loads(tool_result.content[0].text)
                assert result["status"] == "COMPLETED"
                assert result["_contract"]["orders_enabled"] is False
                assert result["llm_controller"] == "external_mcp_client"
                evidence = await session.call_tool(
                    "get_research_evidence", {"research_run_id": result["research_run_id"]}
                )
                assert evidence.is_error is not True

    asyncio.run(check())
    events = EvidenceStore(tmp_path / "state").events()
    assert [x["kind"] for x in events].count("run") == 1
    assert [x["kind"] for x in events].count("attempt") == 1
    assert [x["kind"] for x in events].count("end") == 1
