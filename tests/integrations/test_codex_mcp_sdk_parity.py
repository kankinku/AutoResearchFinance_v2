from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from mcp import types
from mcp.server import ServerRequestContext

from integrations.codex_mcp_sdk_server import (
    SDK_ADAPTER_STATUS,
    SDKMCPServerAdapter,
    create_sdk_mcp_server,
)
from integrations.codex_mcp_server import _tools

PUBLIC_NAMES = {
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

LEGACY_CALLS: tuple[tuple[str, dict[str, object], str], ...] = (
    ("set_research_mode", {"mode": "paper"}, "LEGACY_INTERNAL_TOOL"),
    ("validate_research_cache", {}, "LEGACY_INTERNAL_TOOL"),
    (
        "plan_generation",
        {
            "parent_ids": ["phase5-parent"],
            "method": "random",
            "count": 1,
            "seed": 0,
        },
        "LEGACY_INTERNAL_TOOL",
    ),
    ("get_research_context", {}, "LEGACY_INTERNAL_TOOL"),
    (
        "submit_research_intent",
        {
            "mode": "structure",
            "parent_ids": ["phase5-parent"],
            "operations": [],
            "rationale": "phase5 sdk compatibility",
        },
        "DEPRECATED",
    ),
)


def _context() -> ServerRequestContext[Any]:
    return cast(ServerRequestContext[Any], None)


def _payload(result: types.CallToolResult) -> dict[str, object]:
    assert len(result.content) == 1
    item = result.content[0]
    assert isinstance(item, types.TextContent)
    payload = json.loads(item.text)
    assert isinstance(payload, dict)
    return payload


def _call(
    adapter: SDKMCPServerAdapter,
    name: str,
    arguments: dict[str, object],
) -> types.CallToolResult:
    result = asyncio.run(
        adapter.call_tool(
            _context(),
            types.CallToolRequestParams(name=name, arguments=arguments),
        )
    )
    assert isinstance(result, types.CallToolResult)
    return result


def test_phase5_3_sdk_tools_match_manual_public_schema_exactly(tmp_path: Path) -> None:
    adapter = create_sdk_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    result = asyncio.run(adapter.list_tools(_context(), None))
    dumped = [
        tool.model_dump(by_alias=True, exclude_none=True)
        for tool in result.tools
    ]

    assert SDK_ADAPTER_STATUS == "CANONICAL_SDK"
    assert dumped == _tools()
    assert {tool.name for tool in result.tools} == PUBLIC_NAMES

    options = adapter.server.create_initialization_options()
    assert options.capabilities.tools is not None


def test_phase5_3_hidden_legacy_calls_work_without_being_advertised(tmp_path: Path) -> None:
    adapter = create_sdk_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    listed = asyncio.run(adapter.list_tools(_context(), None))
    listed_names = {tool.name for tool in listed.tools}

    for name, arguments, expected_status in LEGACY_CALLS:
        assert name not in listed_names
        result = _call(adapter, name, arguments)
        assert result.is_error is False
        payload = _payload(result)
        compatibility = payload["_compatibility"]
        assert isinstance(compatibility, dict)
        assert compatibility["status"] == expected_status


def test_phase5_3_public_contract_metadata_is_preserved(tmp_path: Path) -> None:
    adapter = create_sdk_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    result = _call(adapter, "initialize_research_state", {})
    assert result.is_error is False
    payload = _payload(result)
    assert payload["_contract"] == {
        "schema_version": 1,
        "tool": "initialize_research_state",
        "plane": "BOOTSTRAP_CONFIGURATION",
        "orders_enabled": False,
    }


def test_phase5_3_sdk_errors_are_sanitized_like_manual_transport(tmp_path: Path) -> None:
    adapter = create_sdk_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )
    outside = tmp_path.parent / "SECRET_STRATEGY_PATH.json"

    result = _call(
        adapter,
        "validate_strategy",
        {"source_path": str(outside)},
    )

    assert result.is_error is True
    payload = _payload(result)
    assert payload == {"status": "ERROR", "message": "tool request failed"}
    assert str(outside) not in json.dumps(
        result.model_dump(by_alias=True),
        ensure_ascii=False,
    )


def test_phase5_3_unknown_tool_is_sanitized(tmp_path: Path) -> None:
    adapter = create_sdk_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    result = _call(adapter, "unknown-secret-tool", {"secret": "DO_NOT_ECHO"})

    assert result.is_error is True
    assert _payload(result) == {
        "status": "ERROR",
        "message": "tool request failed",
    }
    assert "DO_NOT_ECHO" not in json.dumps(
        result.model_dump(by_alias=True),
        ensure_ascii=False,
    )
