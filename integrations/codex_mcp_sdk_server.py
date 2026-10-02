from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any, cast

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

from integrations.codex_mcp_core import (
    CodexMCPServer,
    _tools,
    _with_legacy_compatibility,
    _with_public_contract,
)
from integrations.codex_mcp_payload import text_content_payload
from research.llm.codex_exec import write_provider_status

SDK_ADAPTER_STATUS = "CANONICAL_SDK"
_SERVER_NAME = "quant-autoresearch"
_SERVER_VERSION = "0.1.0"


class SDKMCPServerAdapter:
    """Official-SDK adapter sharing the canonical MCP application dispatch."""

    def __init__(self, *, state_dir: Path, project_root: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.project_root = project_root.resolve()
        self.dispatcher = CodexMCPServer(
            state_dir=self.state_dir,
            project_root=self.project_root,
        )
        self.server: Server[Any] = Server(
            _SERVER_NAME,
            version=_SERVER_VERSION,
            description=(
                "Official-SDK adapter for quant-autoresearch. "
                "Tool schema and dispatch parity are preserved after canonical cutover."
            ),
            on_list_tools=self.list_tools,
            on_call_tool=self.call_tool,
        )

    async def list_tools(
        self,
        _context: ServerRequestContext[Any],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        write_provider_status(
            self.state_dir / "llm" / "status.json",
            "codex_desktop",
            "ONLINE",
            "MCP_CONNECTED",
        )
        return types.ListToolsResult(
            tools=[_sdk_tool(tool) for tool in _tools()],
        )

    async def call_tool(
        self,
        _context: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        arguments = params.arguments or {}
        try:
            payload = self.dispatcher._dispatch(params.name, dict(arguments))
            payload = _with_legacy_compatibility(params.name, payload)
            payload = _with_public_contract(params.name, payload)
        except (OSError, PermissionError, TypeError, ValueError):
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"},
                is_error=True,
            )
        return _sdk_tool_result(payload, is_error=False)

    async def serve_stdio(self) -> None:
        """Serve the official SDK adapter over stdio."""

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


def create_sdk_mcp_server(*, state_dir: Path, project_root: Path) -> SDKMCPServerAdapter:
    return SDKMCPServerAdapter(
        state_dir=state_dir,
        project_root=project_root,
    )


def main(
    argv: list[str] | None = None,
    *,
    prog: str = "quant-autoresearch-sdk-shadow",
) -> int:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    adapter = create_sdk_mcp_server(
        state_dir=args.state_dir,
        project_root=args.project_root,
    )
    asyncio.run(adapter.serve_stdio())
    return 0


def _sdk_tool(definition: dict[str, object]) -> types.Tool:
    name = definition.get("name")
    description = definition.get("description")
    input_schema = definition.get("inputSchema")
    if not isinstance(name, str):
        raise TypeError("tool name must be a string")
    if description is not None and not isinstance(description, str):
        raise TypeError("tool description must be a string")
    if not isinstance(input_schema, dict):
        raise TypeError("tool inputSchema must be an object")
    return types.Tool(
        name=name,
        description=description,
        input_schema=cast(dict[str, Any], input_schema),
    )


def _sdk_tool_result(payload: object, *, is_error: bool) -> types.CallToolResult:
    content = text_content_payload(payload)
    text = content[0]["text"]
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        is_error=is_error,
    )


if __name__ == "__main__":
    raise SystemExit(main())
