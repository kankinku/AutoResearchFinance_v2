"""A dedicated ChatGPT MCP tool plane must not expose legacy autonomous controls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from mcp import types
from mcp.server import ServerRequestContext

from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter
from integrations.codex_mcp_core import _tools


def test_chatgpt_plane_does_not_mutate_legacy_public_surface(tmp_path: Path) -> None:
    adapter = create_chatgpt_sdk_adapter(state_dir=tmp_path / "state", project_root=tmp_path)

    async def check() -> None:
        context = cast(ServerRequestContext[Any], None)
        published = await adapter.list_tools(context, None)
        names = {tool.name for tool in published.tools}
        legacy = {str(item["name"]) for item in _tools()}
        assert len(legacy) == 13
        assert len(names) == 23
        assert {"get_research_brief", "run_research_step"} <= names
        assert {"start_system", "stop_system", "check_system", "run_evaluation"}.isdisjoint(names)
        assert len(names & legacy) == 8
        blocked = await adapter.call_tool(
            context, types.CallToolRequestParams(name="start_system", arguments={})
        )
        assert blocked.is_error is True
        item = blocked.content[0]
        assert isinstance(item, types.TextContent)
        assert json.loads(item.text) == {"status": "ERROR", "message": "tool request failed"}

        brief = await adapter.call_tool(
            context, types.CallToolRequestParams(name="get_research_brief", arguments={})
        )
        assert brief.is_error is False
        item = brief.content[0]
        assert isinstance(item, types.TextContent)
        payload = json.loads(item.text)
        assert payload["_contract"]["orders_enabled"] is False
        assert payload["_contract"]["tool"] == "get_research_brief"

    asyncio.run(check())
