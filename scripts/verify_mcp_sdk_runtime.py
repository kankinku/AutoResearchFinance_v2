from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client

_REQUIRED_TOOLS = frozenset(
    {
        "initialize_research_state",
        "get_workspace_status",
        "validate_strategy",
        "import_strategies",
        "list_strategies",
        "list_features",
        "get_research_evidence",
        "get_dashboard_status",
        "run_evaluation",
        "check_system",
        "start_system",
        "get_system_status",
        "stop_system",
    }
)

_LEGACY_COMPATIBILITY: dict[str, tuple[str, dict[str, Any]]] = {
    "set_research_mode": ("LEGACY_INTERNAL_TOOL", {"mode": "paper"}),
    "validate_research_cache": ("LEGACY_INTERNAL_TOOL", {}),
    "plan_generation": (
        "LEGACY_INTERNAL_TOOL",
        {
            "parent_ids": ["acceptance-parent"],
            "method": "random",
            "count": 1,
            "seed": 0,
        },
    ),
    "get_research_context": ("LEGACY_INTERNAL_TOOL", {}),
    "submit_research_intent": (
        "DEPRECATED",
        {
            "mode": "structure",
            "parent_ids": ["acceptance-parent"],
            "operations": [],
            "rationale": "sdk stdio compatibility acceptance",
        },
    ),
}

_LEGACY_PROTOCOL_VERSION = "2024-11-05"
_EXPECTED_SDK_PROTOCOL_VERSION = "2025-11-25"
_SERVER_NAME = "quant-autoresearch"


def run_acceptance(
    *,
    project_root: Path,
    state_dir: Path,
    python_executable: str | None = None,
    timeout: float = 30.0,
) -> dict[str, object]:
    root = project_root.resolve()
    state = state_dir.resolve()
    executable = python_executable or sys.executable

    _assert_manual_entrypoint_remains_canonical(root)

    try:
        sdk_result = asyncio.run(
            _run_session_acceptance(
                project_root=root,
                state_dir=state / "negotiated",
                python_executable=executable,
                timeout=timeout,
                protocol_version=None,
            )
        )
        legacy_result = asyncio.run(
            _run_session_acceptance(
                project_root=root,
                state_dir=state / "legacy-2024",
                python_executable=executable,
                timeout=timeout,
                protocol_version=_LEGACY_PROTOCOL_VERSION,
            )
        )
    except Exception as exc:
        raise RuntimeError("SDK MCP acceptance failed") from exc

    if sdk_result["protocol_version"] != _EXPECTED_SDK_PROTOCOL_VERSION:
        raise RuntimeError("SDK MCP negotiated protocol mismatch")
    if legacy_result["protocol_version"] != _LEGACY_PROTOCOL_VERSION:
        raise RuntimeError("legacy MCP protocol compatibility mismatch")

    for key in (
        "server_name",
        "tool_count",
        "public_contract_schema_version",
        "legacy_compatibility_count",
        "system_status",
        "orders_enabled",
    ):
        if sdk_result[key] != legacy_result[key]:
            raise RuntimeError("SDK and legacy MCP acceptance results diverged")

    return {
        "status": "PASS",
        "sdk_protocol_version": sdk_result["protocol_version"],
        "legacy_protocol_version": legacy_result["protocol_version"],
        "server_name": sdk_result["server_name"],
        "tool_count": sdk_result["tool_count"],
        "public_contract_schema_version": sdk_result["public_contract_schema_version"],
        "legacy_compatibility_count": sdk_result["legacy_compatibility_count"],
        "system_status": sdk_result["system_status"],
        "canonical_entrypoint": "manual",
        "orders_enabled": False,
    }


async def _run_session_acceptance(
    *,
    project_root: Path,
    state_dir: Path,
    python_executable: str,
    timeout: float,
    protocol_version: str | None,
) -> dict[str, object]:
    parameters = StdioServerParameters(
        command=python_executable,
        args=[
            "-m",
            "integrations.codex_mcp_sdk_server",
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(project_root),
        ],
        cwd=project_root,
    )
    client_info = types.Implementation(
        name="phase5-sdk-acceptance",
        version="1",
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timeout,
            client_info=client_info,
        ) as session:
            if protocol_version is None:
                initialize = await session.initialize()
            else:
                initialize = await _initialize_with_protocol(
                    session,
                    protocol_version=protocol_version,
                    client_info=client_info,
                )

            if initialize.server_info.name != _SERVER_NAME:
                raise RuntimeError("SDK MCP server identity mismatch")

            tools_result = await session.list_tools()
            tool_names = {tool.name for tool in tools_result.tools}
            if tool_names != _REQUIRED_TOOLS:
                raise RuntimeError("SDK MCP public tool surface mismatch")

            status_result = await session.call_tool("get_system_status", {})
            status_payload = _tool_payload(status_result)
            contract = status_payload.get("_contract")
            if contract != {
                "schema_version": 1,
                "tool": "get_system_status",
                "plane": "EVIDENCE_STATUS",
                "orders_enabled": False,
            }:
                raise RuntimeError("SDK MCP public response contract mismatch")

            system_status = status_payload.get("status")
            if not isinstance(system_status, str):
                raise RuntimeError("SDK MCP system status is invalid")

            for name, (expected_status, arguments) in _LEGACY_COMPATIBILITY.items():
                if name in tool_names:
                    raise RuntimeError("SDK MCP legacy tool was advertised")
                result = await _call_unlisted_tool(
                    session,
                    name=name,
                    arguments=arguments,
                )
                payload = _tool_payload(result)
                compatibility = payload.get("_compatibility")
                if not isinstance(compatibility, dict):
                    raise RuntimeError("SDK MCP legacy compatibility metadata missing")
                if compatibility.get("status") != expected_status:
                    raise RuntimeError("SDK MCP legacy compatibility status mismatch")
                if "_contract" in payload:
                    raise RuntimeError("SDK MCP legacy tool received a public contract")
                if payload.get("orders_enabled") is True:
                    raise RuntimeError("SDK MCP legacy tool exposed order capability")

            secret_path = state_dir.parent / "SECRET_SDK_ACCEPTANCE_PATH.json"
            rejected = await session.call_tool(
                "validate_strategy",
                {"source_path": str(secret_path)},
            )
            if not isinstance(rejected, types.CallToolResult) or not rejected.is_error:
                raise RuntimeError("SDK MCP invalid path was not rejected")
            rejected_payload = _tool_payload(rejected, require_success=False)
            if rejected_payload != {
                "status": "ERROR",
                "message": "tool request failed",
            }:
                raise RuntimeError("SDK MCP error sanitization mismatch")
            rejected_wire = json.dumps(
                rejected.model_dump(by_alias=True, exclude_none=True),
                ensure_ascii=False,
            )
            if str(secret_path) in rejected_wire:
                raise RuntimeError("SDK MCP error leaked a rejected path")

            return {
                "protocol_version": initialize.protocol_version,
                "server_name": initialize.server_info.name,
                "tool_count": len(tool_names),
                "public_contract_schema_version": 1,
                "legacy_compatibility_count": len(_LEGACY_COMPATIBILITY),
                "system_status": system_status,
                "orders_enabled": False,
            }


async def _call_unlisted_tool(
    session: ClientSession,
    *,
    name: str,
    arguments: dict[str, Any],
) -> types.CallToolResult:
    return await session.send_request(
        types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(
                name=name,
                arguments=arguments,
            ),
        ),
        types.CallToolResult,
    )


async def _initialize_with_protocol(
    session: ClientSession,
    *,
    protocol_version: str,
    client_info: types.Implementation,
) -> types.InitializeResult:
    result = await session.send_request(
        types.InitializeRequest(
            params=types.InitializeRequestParams(
                protocol_version=protocol_version,
                capabilities=types.ClientCapabilities(),
                client_info=client_info,
            )
        ),
        types.InitializeResult,
    )
    if result.protocol_version != protocol_version:
        raise RuntimeError("SDK MCP legacy protocol negotiation mismatch")
    session.adopt(result)
    await session.send_notification(types.InitializedNotification())
    return result


def _tool_payload(
    result: object,
    *,
    require_success: bool = True,
) -> dict[str, Any]:
    if not isinstance(result, types.CallToolResult):
        raise RuntimeError("SDK MCP tool returned a non-tool result")
    if require_success and result.is_error:
        raise RuntimeError("SDK MCP tool returned an error")
    if len(result.content) != 1 or not isinstance(result.content[0], types.TextContent):
        raise RuntimeError("SDK MCP tool result has invalid content")
    try:
        payload = json.loads(result.content[0].text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("SDK MCP tool text is not JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("SDK MCP tool payload is invalid")
    return payload


def _assert_manual_entrypoint_remains_canonical(project_root: Path) -> None:
    path = project_root / "integrations" / "codex_mcp_server.py"
    text = path.read_text(encoding="utf-8")
    if "from integrations.codex_mcp_protocol import" not in text or "serve_lines(" not in text:
        raise RuntimeError("manual MCP entrypoint is no longer canonical")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the official-SDK MCP shadow server over real stdio subprocesses."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--state-dir", default="state/mcp-sdk-acceptance")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    state_dir = Path(args.state_dir)
    if not state_dir.is_absolute():
        state_dir = (project_root / state_dir).resolve()

    try:
        result = run_acceptance(
            project_root=project_root,
            state_dir=state_dir,
            python_executable=args.python,
            timeout=args.timeout,
        )
    except RuntimeError:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_class": "RuntimeError",
                    "message": "SDK MCP acceptance failed",
                    "orders_enabled": False,
                },
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
