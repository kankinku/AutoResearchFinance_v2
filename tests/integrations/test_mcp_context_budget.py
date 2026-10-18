"""The GPT-facing transport must not echo unbounded stored research history."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from mcp import types
from mcp.server import ServerRequestContext

from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter
from integrations.mcp_context_budget import compact_mcp_context, encoded_size


def _large_dashboard() -> dict[str, object]:
    return {
        "health": {"status": "READY"},
        "research": {"generation": 181, "orders_enabled": False},
        "tests": [{"generation": i, "results": "x" * 6000} for i in range(100)],
        "trend": [{"generation": i, "return": i / 10} for i in range(100)],
        "workers": [{"id": i, "state": "COMPLETED"} for i in range(100)],
    }


def test_dashboard_summary_is_bounded_without_changing_original() -> None:
    original = _large_dashboard()
    before = encoded_size(original)
    reduced = compact_mcp_context("get_dashboard_status", original)
    assert encoded_size(reduced) <= 24 * 1024
    assert reduced["health"] == original["health"]
    assert reduced["research"] == original["research"]
    assert len(cast(list[object], reduced["tests"])) < 100
    assert reduced["_context_budget"]["original_bytes"] == before
    assert reduced["_context_budget"]["stored_records_unchanged"] is True
    assert len(cast(list[object], original["tests"])) == 100
    assert compact_mcp_context("get_dashboard_status", original, response_mode="full") is original


def test_research_brief_bounded_and_preserves_essential_research_fields() -> None:
    original: dict[str, object] = {
        "orders_enabled": False,
        "generation": 180,
        "champion": {"id": "parent-180", "return": 0.33},
        "research_inputs": {"data_path": "market.parquet"},
        "research_execution_policy": {"trading": False},
        "frontier": [{"id": f"p{i}"} for i in range(30)],
        "feature_catalog": [{"name": f"indicator{i}", "explain": "x" * 1000} for i in range(100)],
        "failure_knowledge": [{"id": i, "reason": "x" * 1200} for i in range(40)],
        "research_trial_inventory": {"counts": 30, "huge_history": ["x" * 1000] * 100},
    }
    small = compact_mcp_context("get_research_brief", original)
    assert encoded_size(small) <= 24 * 1024
    for field in (
        "orders_enabled",
        "generation",
        "champion",
        "research_inputs",
        "research_execution_policy",
    ):
        assert small[field] == original[field]
    assert small["_context_budget"]["mode"] == "summary"


def test_small_payload_and_action_payload_never_change() -> None:
    original = {"checkpoint_token": "abc", "generation": 3, "next_action": "SUBMIT_DIAGNOSIS"}
    assert compact_mcp_context("get_dashboard_status", original) is original
    assert compact_mcp_context("submit_algorithm_plan", _large_dashboard()) == _large_dashboard()


def test_chatgpt_adapter_summary_default_and_explicit_full(tmp_path: Path) -> None:
    adapter = create_chatgpt_sdk_adapter(state_dir=tmp_path / "state", project_root=tmp_path)
    original = _large_dashboard()

    def fake_dispatch(name: str, arguments: dict[str, Any]) -> dict[str, object]:
        assert name == "get_dashboard_status"
        assert arguments == {}
        return original

    adapter.dispatcher._dispatch = fake_dispatch  # type: ignore[method-assign]

    async def check() -> None:
        context = cast(ServerRequestContext[Any], None)
        tools = await adapter.list_tools(context, None)
        tool = next(item for item in tools.tools if item.name == "get_dashboard_status")
        assert "response_mode" in tool.input_schema["properties"]
        result = await adapter.call_tool(
            context, types.CallToolRequestParams(name="get_dashboard_status", arguments={})
        )
        assert not result.is_error
        payload = json.loads(cast(types.TextContent, result.content[0]).text)
        assert encoded_size(payload) <= 24 * 1024
        assert payload["_context_budget"]["mode"] == "summary"
        full = await adapter.call_tool(
            context,
            types.CallToolRequestParams(
                name="get_dashboard_status", arguments={"response_mode": "full"}
            ),
        )
        assert not full.is_error
        full_payload = json.loads(cast(types.TextContent, full.content[0]).text)
        assert {k: v for k, v in full_payload.items() if k != "_contract"} == original
        assert full_payload["_contract"]["orders_enabled"] is False
        invalid = await adapter.call_tool(
            context,
            types.CallToolRequestParams(
                name="get_dashboard_status", arguments={"response_mode": "disable_security"}
            ),
        )
        assert invalid.is_error

    asyncio.run(check())
    metrics = (tmp_path / "state" / "logs" / "mcp-context-metrics.jsonl").read_text()
    assert "results" not in metrics
    assert '"original_bytes"' in metrics
