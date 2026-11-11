"""Freeze the user-approved 32-name ChatGPT MCP ABI separately from registry code."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import types
from mcp.server import ServerRequestContext

from integrations import chatgpt_mcp_sdk as sdk

APPROVED_TOOL_NAMES = frozenset({
    "audit_market_data",
    "cancel_algorithm_research",
    "cancel_research_batch",
    "download_market_data",
    "evaluate_algorithm_experiments",
    "get_algorithm_research",
    "get_dashboard_status",
    "get_guided_research",
    "get_research_batch_report",
    "get_research_batch_status",
    "get_research_brief",
    "get_research_evidence",
    "get_workspace_status",
    "import_strategies",
    "initialize_research_state",
    "list_features",
    "list_market_data",
    "list_strategies",
    "preflight_research_batch",
    "reconcile_algorithm_research",
    "reconcile_guided_research",
    "resume_algorithm_research",
    "resume_research_batch",
    "run_research_step",
    "start_algorithm_research",
    "start_guided_research",
    "start_research_batch",
    "submit_algorithm_diagnosis",
    "submit_algorithm_plan",
    "submit_guided_generation",
    "validate_market_data",
    "validate_strategy",
})


def test_chatgpt_public_inventory_matches_frozen_32_names() -> None:
    tools = sdk.chatgpt_tools()
    names = [item["name"] for item in tools]
    assert len(names) == len(set(names)) == len(APPROVED_TOOL_NAMES) == 32
    assert set(names) == APPROVED_TOOL_NAMES
    assert "suggest_guided_thresholds" not in names
    assert {"start_system", "stop_system", "run_evaluation"}.isdisjoint(names)


def test_unauthorized_33rd_tool_rejected_even_without_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sdk, "_CHATGPT_CANONICAL", sdk._CHATGPT_CANONICAL | {"start_system"}
    )
    with pytest.raises(TypeError, match="approved.*inventory"):
        sdk.chatgpt_tools()


def test_unapproved_same_count_name_swap_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sdk, "_CHATGPT_CANONICAL",
        (sdk._CHATGPT_CANONICAL - {"get_workspace_status"}) | {"start_system"},
    )
    with pytest.raises(TypeError, match="approved.*inventory"):
        sdk.chatgpt_tools()


def test_unlisted_registry_entry_is_rejected_before_advertising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        sdk._CHATGPT_CUSTOM, "suggest_guided_thresholds", "CATALOG_VALIDATION"
    )
    with pytest.raises(TypeError, match="approved.*inventory"):
        sdk.chatgpt_tools()


def test_tool_registry_cannot_enable_unadvertised_tool_after_adapter_init(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = sdk.create_chatgpt_sdk_adapter(
        state_dir=tmp_path / "state", project_root=tmp_path,
    )
    monkeypatch.setitem(sdk._CHATGPT_CUSTOM, "start_system", "EXECUTION_LIFECYCLE")

    async def check() -> None:
        result = await adapter.call_tool(
            cast(ServerRequestContext[Any], None),
            types.CallToolRequestParams(name="start_system", arguments={}),
        )
        assert result.is_error is True
        assert isinstance(result.content[0], types.TextContent)
        assert json.loads(result.content[0].text) == {
            "status": "ERROR", "message": "tool request failed"
        }

    asyncio.run(check())


def test_oauth_tool_list_preserves_exact_names_and_scopes(
    tmp_path: Path,
) -> None:
    adapter = sdk.create_chatgpt_sdk_adapter(
        state_dir=tmp_path / "state", project_root=tmp_path, require_oauth=True,
    )

    async def check() -> None:
        context = cast(ServerRequestContext[Any], None)
        listed = await adapter.list_tools(context, None)
        payload = listed.model_dump(by_alias=True, exclude_none=True)
        tools = payload["tools"]
        assert len(tools) == 32
        assert {item["name"] for item in tools} == APPROVED_TOOL_NAMES
        assert all(
            item["securitySchemes"] == [
                {"type": "oauth2", "scopes": ["mcp:tools"]}
            ]
            for item in tools
        )
        forbidden = await adapter.call_tool(
            context,
            types.CallToolRequestParams(
                name="suggest_guided_thresholds",
                arguments={"session_id": "a" * 32, "feature_id": "secret"},
            ),
        )
        assert forbidden.is_error is True

    asyncio.run(check())


def test_existing_chatgpt_and_codex_schema_hashes_remain_identical_to_main() -> None:
    from core.integrity.hashes import content_hash
    from integrations.codex_mcp_core import _tools

    # Actual main-branch baseline, not a hash computed from mutable registries.
    assert content_hash(sdk.chatgpt_tools()) == (
        "badef8286b177181601b4fe88c561f9f4cd121172c5fc90ec74748661192ac87"
    )
    assert content_hash(_tools()) == (
        "e11cfcce0a830f5a3cfc9a1f570c0cb21de25960d3876b11757fe7c7a1fed5ce"
    )
