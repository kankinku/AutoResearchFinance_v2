"""The dedicated launcher works for a local process or Docker-exec tunnel."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent

ROOT = Path(__file__).resolve().parents[2]


def test_standalone_launcher_uses_worktree_and_correct_tool_plane() -> None:
    launcher = ROOT / "scripts" / "run_chatgpt_mcp_stdio.sh"

    async def check() -> None:
        params = StdioServerParameters(command="bash", args=[str(launcher)], cwd=Path("/tmp"))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 11
                assert not any(tool.name == "start_system" for tool in tools.tools)
                result = await session.call_tool("get_research_brief", {})
                assert result.is_error is not True
                assert isinstance(result.content[0], TextContent)
                payload = json.loads(result.content[0].text)
                assert payload["_contract"]["orders_enabled"] is False

    asyncio.run(check())
