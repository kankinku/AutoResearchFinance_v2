"""Isolated ChatGPT-facing MCP surface; legacy 13-tool public ABI stays frozen."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import ServerRequestContext

from application.mcp_contracts import PublicToolContractMetadata, PublicToolPlane
from integrations.codex_mcp_core import _chat_directed_step_schema, _tools
from integrations.codex_mcp_sdk_server import (
    SDKMCPServerAdapter,
    _sdk_tool,
    _sdk_tool_result,
)

_CHATGPT_CANONICAL = frozenset(
    {
        "initialize_research_state",
        "get_workspace_status",
        "validate_strategy",
        "import_strategies",
        "list_strategies",
        "list_features",
        "get_research_evidence",
        "get_dashboard_status",
        "get_system_status",
    }
)
_CHATGPT_CUSTOM: dict[str, PublicToolPlane] = {
    "get_research_brief": "EVIDENCE_STATUS",
    "run_research_step": "EXECUTION_LIFECYCLE",
}


def chatgpt_tools() -> list[dict[str, object]]:
    """Advertise no autonomous Codex start/stop and no broker/order operations."""
    canonical = [item for item in _tools() if item["name"] in _CHATGPT_CANONICAL]
    custom: list[dict[str, object]] = [
        {
            "name": "get_research_brief",
            "description": "Read sanitized research context, Frontier and prior failure evidence.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "run_research_step",
            "description": (
                "Execute one external GPT-authored ResearchIntent against canonical Strategy IR; "
                "strict mutation validation and immutable Evidence, never place orders."
            ),
            "inputSchema": _chat_directed_step_schema(),
        },
    ]
    return canonical + custom


class ChatGPTMCPAdapter(SDKMCPServerAdapter):
    """Distinct official SDK tool plane with no local-LLM autonomous actions."""

    async def list_tools(
        self,
        _context: ServerRequestContext[Any],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[_sdk_tool(item) for item in chatgpt_tools()])

    async def call_tool(
        self,
        _context: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        if params.name not in (_CHATGPT_CANONICAL | _CHATGPT_CUSTOM.keys()):
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"}, is_error=True
            )
        result = await super().call_tool(_context, params)
        if result.is_error or params.name not in _CHATGPT_CUSTOM:
            return result
        content = result.content[0]
        if not isinstance(content, types.TextContent):
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"}, is_error=True
            )
        payload = json.loads(content.text)
        if not isinstance(payload, dict):
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"}, is_error=True
            )
        payload["_contract"] = PublicToolContractMetadata(
            tool=params.name, plane=_CHATGPT_CUSTOM[params.name], orders_enabled=False
        ).model_dump(mode="json")
        return _sdk_tool_result(payload, is_error=False)


def create_chatgpt_sdk_adapter(*, state_dir: Path, project_root: Path) -> ChatGPTMCPAdapter:
    return ChatGPTMCPAdapter(state_dir=state_dir, project_root=project_root)
