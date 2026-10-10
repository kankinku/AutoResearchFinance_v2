"""Isolated ChatGPT-facing MCP surface; legacy 13-tool public ABI stays frozen."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import ServerRequestContext
from pydantic import Field, field_serializer

from application.mcp_contracts import PublicToolContractMetadata, PublicToolPlane
from application.research_batch_service import MAX_CANDIDATES, MAX_GENERATIONS
from integrations.codex_mcp_core import _chat_directed_step_schema, _tools
from integrations.codex_mcp_sdk_server import (
    SDKMCPServerAdapter,
    _sdk_tool,
    _sdk_tool_result,
)
from integrations.quant_mcp_diagnostics import MCPAuditLog

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
    }
)
_CHATGPT_CUSTOM: dict[str, PublicToolPlane] = {
    "get_research_brief": "EVIDENCE_STATUS",
    "run_research_step": "EXECUTION_LIFECYCLE",
    "start_research_batch": "EXECUTION_LIFECYCLE",
    "get_research_batch_status": "EVIDENCE_STATUS",
    "get_research_batch_report": "EVIDENCE_STATUS",
    "cancel_research_batch": "EXECUTION_LIFECYCLE",
    "list_market_data": "EVIDENCE_STATUS",
    "validate_market_data": "CATALOG_VALIDATION",
    "download_market_data": "EXECUTION_LIFECYCLE",
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
    step_schema = _chat_directed_step_schema()
    step_properties = step_schema["properties"]
    if not isinstance(step_properties, dict):
        raise TypeError("research step tool properties are invalid")
    batch_schema = {
        **step_schema,
        "properties": {
            **step_properties,
            "generations": {"type": "integer", "minimum": 1, "maximum": MAX_GENERATIONS},
            "count": {"type": "integer", "minimum": 1, "maximum": MAX_CANDIDATES},
        },
        "required": ["source_path", "data_path", "intent", "generations"],
    }
    status_schema = {
        "type": "object",
        "properties": {"job_id": {"type": "string", "description": "Omit for most recent batch"}},
        "additionalProperties": False,
    }
    custom.extend(
        [
            {
                "name": "start_research_batch",
                "description": "Execute a bounded 1-100 generation GPT-planned research batch. "
                "No local LLM calls; returns job ID, status and measured ETA.",
                "inputSchema": batch_schema,
            },
            {
                "name": "get_research_batch_status",
                "description": "Check batch completion, progress and historically measured ETA.",
                "inputSchema": status_schema,
            },
            {
                "name": "get_research_batch_report",
                "description": "Report generation times, verified successor IDs and funnel counts. "
                "Final report only after completion; no OOS approval implied.",
                "inputSchema": status_schema,
            },
            {
                "name": "cancel_research_batch",
                "description": "Stop after current generation; retain completed Evidence.",
                "inputSchema": status_schema,
            },
        ]
    )
    custom.extend(
        [
            {
                "name": "list_market_data",
                "description": (
                    "List exact local immutable market-data paths and whether read-only "
                    "Tiingo/KIS sources are configured. No credentials or rows exposed."
                ),
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "validate_market_data",
                "description": (
                    "Inspect existing managed Parquet OHLCV, declared lineage and quality."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"data_path": {"type": "string"}},
                    "required": ["data_path"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "download_market_data",
                "description": (
                    "Explicitly fetch US equity/ETF daily prices from configured read-only "
                    "Tiingo or KIS, verify date coverage, and save immutable development "
                    "Parquet. No account orders, API keys, or arbitrary URLs accepted."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string", "enum": ["tiingo", "kis"]},
                        "symbol": {"type": "string", "minLength": 1, "maxLength": 15},
                        "start": {"type": "string", "format": "date"},
                        "end": {"type": "string", "format": "date"},
                        "price_policy": {
                            "type": "string",
                            "enum": ["raw", "total_return_adjusted"],
                            "default": "raw",
                        },
                    },
                    "required": ["provider", "symbol", "start", "end"],
                    "additionalProperties": False,
                },
            },
        ]
    )
    return canonical + custom


class _OAuthTool(types.Tool):
    """Published per-tool OAuth security declaration for OpenAI clients."""

    security_schemes: list[dict[str, object]] = Field(alias="securitySchemes")


class _OAuthToolsResult(types.ListToolsResult):
    @field_serializer("tools")
    def serialize_tools(self, tools: list[types.Tool]) -> list[dict[str, object]]:
        # SDK's list[Tool] annotation otherwise strips subclass securitySchemes.
        return [tool.model_dump(by_alias=True, exclude_none=True) for tool in tools]


class ChatGPTMCPAdapter(SDKMCPServerAdapter):
    """Distinct official SDK tool plane with no local-LLM autonomous actions."""

    def __init__(
        self,
        *,
        state_dir: Path,
        project_root: Path,
        require_oauth: bool = False,
        audit: MCPAuditLog | None = None,
    ) -> None:
        super().__init__(state_dir=state_dir, project_root=project_root)
        self.require_oauth = require_oauth
        self.audit = audit

    async def list_tools(
        self,
        _context: ServerRequestContext[Any],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        tools = [_sdk_tool(item) for item in chatgpt_tools()]
        if self.audit is not None:
            self.audit.emit("tools_list", result="OK", count=len(tools))
        if not self.require_oauth:
            return types.ListToolsResult(tools=tools)
        return _OAuthToolsResult(
            tools=[
                _OAuthTool.model_validate(
                    {
                        **item.model_dump(by_alias=True, exclude_none=True),
                        "securitySchemes": [{"type": "oauth2", "scopes": ["mcp:tools"]}],
                    }
                )
                for item in tools
            ]
        )

    async def call_tool(
        self,
        _context: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        if params.name not in (_CHATGPT_CANONICAL | _CHATGPT_CUSTOM.keys()):
            if self.audit is not None:
                self.audit.emit(
                    "tool_call", tool="unknown", result="ERROR", error_code="UNKNOWN_TOOL"
                )
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"}, is_error=True
            )
        result = await super().call_tool(_context, params)
        if self.audit is not None:
            error_code = None
            if (
                result.is_error
                and result.content
                and isinstance(result.content[0], types.TextContent)
            ):
                try:
                    error_code = json.loads(result.content[0].text).get("error_code")
                except (ValueError, AttributeError):
                    pass
            self.audit.emit(
                "tool_call",
                tool=params.name,
                result="ERROR" if result.is_error else "OK",
                error_code=error_code or ("TOOL_EXECUTION_FAILED" if result.is_error else None),
            )
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


def create_chatgpt_sdk_adapter(
    *,
    state_dir: Path,
    project_root: Path,
    require_oauth: bool = False,
    audit: MCPAuditLog | None = None,
) -> ChatGPTMCPAdapter:
    return ChatGPTMCPAdapter(
        state_dir=state_dir,
        project_root=project_root,
        require_oauth=require_oauth,
        audit=audit,
    )
