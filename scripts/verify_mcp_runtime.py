from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

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

_LEGACY_COMPATIBILITY = {
    "set_research_mode": "LEGACY_INTERNAL_TOOL",
    "validate_research_cache": "LEGACY_INTERNAL_TOOL",
    "plan_generation": "LEGACY_INTERNAL_TOOL",
    "get_research_context": "LEGACY_INTERNAL_TOOL",
    "submit_research_intent": "DEPRECATED",
}


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
    requests = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "phase3-host-acceptance", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_system_status", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "set_research_mode", "arguments": {"mode": "paper"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "validate_research_cache", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "plan_generation",
                "arguments": {
                    "parent_ids": ["acceptance-parent"],
                    "method": "random",
                    "count": 1,
                    "seed": 0,
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "get_research_context", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "submit_research_intent",
                "arguments": {
                    "mode": "structure",
                    "parent_ids": ["acceptance-parent"],
                    "operations": [],
                    "rationale": "stdio compatibility acceptance",
                },
            },
        },
    )
    request_text = "".join(json.dumps(item, sort_keys=True) + "\n" for item in requests)
    try:
        completed = subprocess.run(
            [
                executable,
                "-m",
                "integrations.codex_mcp_manual_server",
                "--state-dir",
                str(state),
                "--project-root",
                str(root),
            ],
            cwd=root,
            input=request_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("MCP server process could not complete") from exc
    if completed.returncode != 0:
        raise RuntimeError("MCP server process exited unsuccessfully")

    responses = _responses(completed.stdout)
    initialize = _response_result(responses, 1)
    tools_result = _response_result(responses, 2)
    status_result = _response_result(responses, 3)
    legacy_results = {
        name: _response_result(responses, request_id)
        for request_id, name in enumerate(_LEGACY_COMPATIBILITY, start=4)
    }

    if initialize.get("protocolVersion") != "2024-11-05":
        raise RuntimeError("MCP protocol version mismatch")
    server_info = initialize.get("serverInfo")
    if not isinstance(server_info, dict) or server_info.get("name") != "quant-autoresearch":
        raise RuntimeError("MCP server identity mismatch")

    tools = tools_result.get("tools")
    if not isinstance(tools, list):
        raise RuntimeError("MCP tools/list returned an invalid payload")
    tool_names = {
        item["name"]
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if tool_names != _REQUIRED_TOOLS:
        raise RuntimeError("MCP public tool surface mismatch")

    if status_result.get("isError") is not False:
        raise RuntimeError("get_system_status returned a tool error")
    system_status = _text_payload(status_result)
    status = system_status.get("status")
    if not isinstance(status, str):
        raise RuntimeError("get_system_status returned an invalid status")
    contract = system_status.get("_contract")
    if not isinstance(contract, dict):
        raise RuntimeError("public MCP response contract is missing")
    if contract != {
        "schema_version": 1,
        "tool": "get_system_status",
        "plane": "EVIDENCE_STATUS",
        "orders_enabled": False,
    }:
        raise RuntimeError("public MCP response contract mismatch")

    for name, expected_status in _LEGACY_COMPATIBILITY.items():
        result = legacy_results[name]
        if result.get("isError") is not False:
            raise RuntimeError(f"legacy compatibility call failed: {name}")
        payload = _text_payload(result)
        compatibility = payload.get("_compatibility")
        if not isinstance(compatibility, dict):
            raise RuntimeError(f"legacy compatibility metadata missing: {name}")
        if compatibility.get("status") != expected_status:
            raise RuntimeError(f"legacy compatibility status mismatch: {name}")
        if "_contract" in payload:
            raise RuntimeError(f"legacy tool incorrectly received public contract: {name}")
        if payload.get("orders_enabled") is True:
            raise RuntimeError(f"legacy tool exposed order capability: {name}")

    return {
        "status": "PASS",
        "transport": "manual_rollback",
        "protocol_version": initialize["protocolVersion"],
        "server_name": server_info["name"],
        "tool_count": len(tool_names),
        "public_contract_schema_version": contract["schema_version"],
        "legacy_compatibility_count": len(legacy_results),
        "system_status": status,
        "orders_enabled": False,
    }


def _responses(stdout: str) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("MCP server emitted invalid JSON-RPC") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("MCP server emitted an invalid response")
        request_id = payload.get("id")
        if isinstance(request_id, int):
            result[request_id] = payload
    if set(result) != set(range(1, 9)):
        raise RuntimeError("MCP server did not return all acceptance responses")
    return result


def _response_result(
    responses: dict[int, dict[str, Any]],
    request_id: int,
) -> dict[str, Any]:
    response = responses[request_id]
    if "error" in response:
        raise RuntimeError(f"MCP JSON-RPC request {request_id} failed")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"MCP JSON-RPC request {request_id} returned no result")
    return result


def _text_payload(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError("MCP tool result has no content")
    first = content[0]
    if not isinstance(first, dict) or not isinstance(first.get("text"), str):
        raise RuntimeError("MCP tool result has invalid text content")
    try:
        payload = json.loads(first["text"])
    except json.JSONDecodeError as exc:
        raise RuntimeError("MCP tool text is not JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("MCP tool text payload is invalid")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the manual rollback MCP stdio transport in a real subprocess."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--state-dir", default="state/mcp-acceptance")
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
    except RuntimeError as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_class": type(exc).__name__,
                    "message": str(exc),
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
