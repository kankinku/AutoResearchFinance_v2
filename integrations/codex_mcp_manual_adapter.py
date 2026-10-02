from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from integrations.codex_mcp_core import (
    CodexMCPServer as CoreCodexMCPServer,
)
from integrations.codex_mcp_core import (
    _tools,
    _with_legacy_compatibility,
    _with_public_contract,
)
from integrations.codex_mcp_protocol import error, success, text_content
from research.llm.codex_exec import write_provider_status


class ManualCodexMCPServer(CoreCodexMCPServer):
    """Legacy 2024-11-05 JSON-RPC adapter retained only for rollback compatibility."""

    def handle(self, request: object) -> dict[str, Any] | None:
        if not isinstance(request, Mapping):
            return error(None, -32600, "invalid request")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return error(request_id, -32600, "method is required")
        if method in {"initialize", "ping", "tools/list"}:
            write_provider_status(
                self.state_dir / "llm" / "status.json",
                "codex_desktop",
                "ONLINE",
                "MCP_CONNECTED",
            )
        if "id" not in request and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return success(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "quant-autoresearch", "version": "0.1.0"},
                },
            )
        if method == "ping":
            return success(request_id, {})
        if method == "tools/list":
            return success(request_id, {"tools": _tools()})
        if method == "tools/call":
            return self._call(request_id, request.get("params"))
        if method == "notifications/initialized":
            return None
        return error(request_id, -32601, "method not found")

    def _call(self, request_id: object, params: object) -> dict[str, Any]:
        if not isinstance(params, Mapping) or not isinstance(params.get("name"), str):
            return error(request_id, -32602, "tool name is required")
        name = str(params["name"])
        arguments = params.get("arguments", {})
        if not isinstance(arguments, Mapping):
            return _tool_error(request_id, "tool arguments must be an object")
        try:
            payload = self._dispatch(name, dict(arguments))
            payload = _with_legacy_compatibility(name, payload)
            payload = _with_public_contract(name, payload)
        except (OSError, PermissionError, TypeError, ValueError):
            return _tool_error(request_id, "tool request failed")
        return success(request_id, {"content": text_content(payload), "isError": False})


def create_manual_mcp_server(
    *,
    state_dir: Path,
    project_root: Path,
) -> ManualCodexMCPServer:
    return ManualCodexMCPServer(
        state_dir=state_dir,
        project_root=project_root,
    )


def _tool_error(request_id: object, message: str) -> dict[str, Any]:
    return success(
        request_id,
        {"content": text_content({"status": "ERROR", "message": message}), "isError": True},
    )
