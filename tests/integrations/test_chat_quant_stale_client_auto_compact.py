"""Compatibility/continuity coverage for cached ChatGPT MCP clients.

The cached client cannot send response_mode. This must not replay all history.
Synthetic history only tests transport scaling, NOT genuine GPT generations.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from mcp import types
from mcp.server import ServerRequestContext

from integrations.academic_chat_compact import compact_academic_checkpoint
from integrations.chatgpt_mcp_sdk import chatgpt_tools, create_chatgpt_sdk_adapter
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _reply(result: types.CallToolResult) -> dict[str, Any]:
    assert result.is_error is False
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return json.loads(block.text)


def test_stale_client_wire_default_is_compact_and_full_is_still_selectable() -> None:
    tools = {tool["name"]: tool for tool in chatgpt_tools()}
    assert len(tools) == 32
    for name in ("get_algorithm_research", "submit_algorithm_plan", "submit_algorithm_diagnosis"):
        fields = tools[name]["inputSchema"]
        assert fields["properties"]["response_mode"]["default"] == "compact"
        assert fields["properties"]["response_mode"]["enum"] == ["full", "compact"]
        assert "response_mode" not in fields["required"]


def test_stale_client_get_plan_diagnosis_and_cross_adapter_recovery(tmp_path: Path) -> None:
    service, started = _setup(tmp_path)
    session_id = started["session_id"]
    planner = ScriptedResearcher()

    async def run() -> None:
        ctx = cast(ServerRequestContext[Any], None)
        one = create_chatgpt_sdk_adapter(state_dir=tmp_path / "state", project_root=tmp_path)
        one.dispatcher._dispatch = service._dispatch  # type: ignore[method-assign]

        async def call(adapter: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return _reply(
                await adapter.call_tool(
                    ctx, types.CallToolRequestParams(name=name, arguments=arguments)
                )
            )

        initial = await call(one, "get_algorithm_research", {"session_id": session_id})
        assert initial["continuation"]["required_model_action"] == "AUTHOR_AND_SUBMIT_PLAN"
        plan = planner.propose(initial["model_context"])
        staged = await call(
            one,
            "submit_algorithm_plan",
            {
                "session_id": session_id,
                "checkpoint_token": initial["checkpoint_token"],
                "plan": plan,
            },
        )
        assert staged["continuation"]["required_model_action"] == "AUTHOR_AND_SUBMIT_DIAGNOSIS"
        diagnosis = planner.propose(staged["model_context"])
        committed = await call(
            one,
            "submit_algorithm_diagnosis",
            {
                "session_id": session_id,
                "checkpoint_token": staged["checkpoint_token"],
                "diagnosis": diagnosis,
            },
        )
        assert committed["completed_generations"] == 1
        assert committed["history_window"]["returned_generations"] == 1
        full = await call(
            one,
            "get_algorithm_research",
            {"session_id": session_id, "response_mode": "full"},
        )
        assert full["history"][-1]["evidence_hash"] == committed["last_completed_evidence_hash"]
        assert full["checkpoint_token"] == committed["checkpoint_token"]
        assert "continuation" not in full

        two = create_chatgpt_sdk_adapter(state_dir=tmp_path / "state", project_root=tmp_path)
        two.dispatcher._dispatch = service._dispatch  # type: ignore[method-assign]
        restored = await call(two, "get_algorithm_research", {"session_id": session_id})
        assert restored["checkpoint_token"] == full["checkpoint_token"]
        assert restored["last_completed_evidence_hash"] == full["history"][-1]["evidence_hash"]
        assert restored["continuation"]["expected_generation"] == 2
        assert restored["continuation"]["required_model_action"] == "AUTHOR_AND_SUBMIT_PLAN"
        authoritative = service._dispatch("get_algorithm_research", {"session_id": session_id})
        assert authoritative["completed_generations"] == 1

    asyncio.run(run())


def test_synthetic_10_25_50_100_history_remains_bounded(tmp_path: Path) -> None:
    service, started = _setup(tmp_path)
    planner = ScriptedResearcher()
    staged = service._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": planner.propose(started["model_context"]),
        },
    )
    finished = service._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": planner.propose(staged["model_context"]),
        },
    )
    transmitted_sizes = []
    raw_sizes = []
    for count in (10, 25, 50, 100):
        scenario = deepcopy(finished)
        scenario["requested_generations"] = 100
        scenario["completed_generations"] = count
        scenario["history"] = []
        for n in range(1, count + 1):
            row = deepcopy(finished["history"][-1])
            row["generation"] = n
            row["evidence_hash"] = f"{n:064x}"
            scenario["history"].append(row)
        view = compact_academic_checkpoint(scenario)
        raw_sizes.append(len(json.dumps(scenario).encode("utf-8")))
        transmitted_sizes.append(len(json.dumps(view).encode("utf-8")))
        assert view["history_window"]["source_generations"] == count
        assert view["history_window"]["returned_generations"] == 1
        assert view["last_completed_evidence_hash"] == f"{count:064x}"
        assert transmitted_sizes[-1] <= 128 * 1024
    assert raw_sizes[-1] > raw_sizes[0] * 4
    assert max(transmitted_sizes) - min(transmitted_sizes) < 2048
