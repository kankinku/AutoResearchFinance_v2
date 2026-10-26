"""Direct ChatGPT Quant: bounded read, resumable phase, safe repair; no Codex model."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import types
from mcp.server import ServerRequestContext

from integrations.academic_chat_compact import (
    ChatCheckpointCompressionError,
    compact_academic_checkpoint,
)
from integrations.chatgpt_mcp_sdk import chatgpt_tools, create_chatgpt_sdk_adapter
from integrations.codex_mcp_sdk_server import _safe_academic_checkpoint_error
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _one_generation(tmp_path: Path) -> tuple[Any, dict[str, Any]]:
    server, state = _setup(tmp_path)
    scripted = ScriptedResearcher()
    plan = scripted.propose(state["model_context"])
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": state["session_id"],
            "checkpoint_token": state["checkpoint_token"],
            "plan": plan,
        },
    )
    diagnosis = scripted.propose(staged["model_context"])
    finished = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": state["session_id"],
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": diagnosis,
        },
    )
    assert finished["completed_generations"] == 1
    return server, finished


def test_schema_adds_opt_in_compact_but_preserves_full_default() -> None:
    tools = {item["name"]: item for item in chatgpt_tools()}
    assert len(tools) == 32
    get = tools["get_algorithm_research"]["inputSchema"]
    assert get["required"] == ["session_id"]
    assert get["properties"]["response_mode"]["enum"] == ["full", "compact"]
    assert get["properties"]["response_mode"]["default"] == "full"
    assert get["additionalProperties"] is False
    for name in ("submit_algorithm_plan", "submit_algorithm_diagnosis"):
        opts = tools[name]["inputSchema"]["properties"]["response_mode"]
        assert opts["enum"] == ["full", "compact"]
        assert opts["default"] == "full"
        assert "response_mode" not in tools[name]["inputSchema"]["required"]


def test_compact_retains_exact_parent_schema_token_and_evidence(tmp_path: Path) -> None:
    _, state = _one_generation(tmp_path)
    original = deepcopy(state)
    compact = compact_academic_checkpoint(state)
    assert state == original  # never mutate original evidence
    assert compact["session_id"] == state["session_id"]
    assert compact["checkpoint_token"] == state["checkpoint_token"]
    assert compact["checkpoint_phase"] == "AWAITING_PLAN"
    assert compact["completed_generations"] == 1
    assert compact["history"] == state["history"][-1:]
    assert (
        compact["model_context"]["algorithm_plan_schema"]
        == state["model_context"]["algorithm_plan_schema"]
    )
    assert (
        compact["model_context"]["selected_development_parent"]
        == state["model_context"]["selected_development_parent"]
    )
    assert compact["last_completed_evidence_hash"] == state["history"][-1]["evidence_hash"]
    assert compact["continuation"]["expected_generation"] == 2
    assert compact["continuation"]["required_model_action"] == "AUTHOR_AND_SUBMIT_PLAN"
    assert compact["continuation"]["automatic_model_turns_started"] == 0
    assert compact["history_window"]["source_generations"] == 1
    assert compact["orders_enabled"] is False
    assert compact["independent_oos_approved"] is False
    assert compact["compact_source"]["complete_history_available_with_full"] is True


def test_pending_diagnosis_keeps_audit_and_schema(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    plan = ScriptedResearcher().propose(started["model_context"])
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": plan,
        },
    )
    slim = compact_academic_checkpoint(staged)
    assert slim["continuation"]["required_model_action"] == "AUTHOR_AND_SUBMIT_DIAGNOSIS"
    assert slim["checkpoint_token"] == staged["checkpoint_token"]
    assert slim["model_context"] == staged["model_context"]
    assert slim["history"] == []


def test_long_history_compression_keeps_provenance_and_reports_omissions(tmp_path: Path) -> None:
    _, original = _one_generation(tmp_path)
    # Synthetic history is for presentation scaling only, NEVER canonical counted evidence.
    scenario = deepcopy(original)
    scenario["history"] = [deepcopy(original["history"][0]) for _ in range(68)]
    scenario["completed_generations"] = 68
    scenario["requested_generations"] = 100
    scenario["model_context"]["generation"] = 69
    for n, event in enumerate(scenario["history"], 1):
        event["generation"] = n
        event["evidence_hash"] = f"{n:064x}"
    view = compact_academic_checkpoint(scenario)
    assert view["history_window"]["source_generations"] == 68
    assert view["history_window"]["returned_generations"] == 1
    assert view["history_window"]["more_history_requires_full_lookup"] is True
    assert view["history"][0]["generation"] == 68
    assert view["last_completed_evidence_hash"] == scenario["history"][-1]["evidence_hash"]
    assert len(json.dumps(view)) < len(json.dumps(scenario))


def test_compact_refuses_invalid_scope_or_over_budget(tmp_path: Path) -> None:
    _, state = _one_generation(tmp_path)
    bad = deepcopy(state)
    bad["orders_enabled"] = True
    with pytest.raises(ChatCheckpointCompressionError, match="orders"):
        compact_academic_checkpoint(bad)
    with pytest.raises(ChatCheckpointCompressionError, match="budget"):
        compact_academic_checkpoint(state, max_bytes=250)


def test_full_and_compact_adapter_dispatch_keep_same_original_checkpoint(tmp_path: Path) -> None:
    server, source = _one_generation(tmp_path)
    adapter = create_chatgpt_sdk_adapter(state_dir=tmp_path / "adapter", project_root=tmp_path)
    adapter.dispatcher._dispatch = server._dispatch  # type: ignore[method-assign]

    async def check() -> None:
        context = cast(ServerRequestContext[Any], None)

        def payload(result: types.CallToolResult) -> dict[str, Any]:
            assert not result.is_error
            block = result.content[0]
            assert isinstance(block, types.TextContent)
            return json.loads(block.text)

        full = payload(
            await adapter.call_tool(
                context,
                types.CallToolRequestParams(
                    name="get_algorithm_research", arguments={"session_id": source["session_id"]}
                ),
            )
        )
        short = payload(
            await adapter.call_tool(
                context,
                types.CallToolRequestParams(
                    name="get_algorithm_research",
                    arguments={"session_id": source["session_id"], "response_mode": "compact"},
                ),
            )
        )
        assert full["history"] == source["history"]
        assert short["history_window"]["source_generations"] == len(full["history"])
        assert short["checkpoint_token"] == full["checkpoint_token"]
        assert full["_contract"] == short["_contract"]
        assert full.get("continuation") is None
        invalid = await adapter.call_tool(
            context,
            types.CallToolRequestParams(
                name="submit_algorithm_plan",
                arguments={"session_id": source["session_id"], "response_mode": "compact"},
            ),
        )
        assert invalid.is_error is True

    asyncio.run(check())


def test_repair_guidance_is_static_and_never_leaks_token() -> None:
    for code in (
        "DUPLICATE_SEMANTIC_PLAN",
        "UNCHANGED_CANONICAL_FILLS",
        "P3_DIAGNOSIS_SEMANTIC_REJECTED",
        "P3_SEMANTIC_PREFLIGHT_REJECTED",
    ):
        result = _safe_academic_checkpoint_error(ValueError(code + ": secret-token-xyz"))
        assert result["retry_same_checkpoint"] is True
        assert result["recovery"]["next_step"] == "READ_CURRENT_CHECKPOINT_THEN_REVISE"
        assert "secret-token-xyz" not in json.dumps(result)
        assert result["orders_enabled"] is False
    unexpected = _safe_academic_checkpoint_error(RuntimeError("private secret-token-xyz"))
    assert unexpected["retry_same_checkpoint"] is False
    assert unexpected["recovery"]["next_step"] == "READ_CURRENT_CHECKPOINT_STOP_IF_UNCERTAIN"
    assert "secret-token-xyz" not in json.dumps(unexpected)


def test_opt_in_compact_plan_and_diagnosis_avoid_big_write_results(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    adapter = create_chatgpt_sdk_adapter(state_dir=tmp_path / "adapter", project_root=tmp_path)
    adapter.dispatcher._dispatch = server._dispatch  # type: ignore[method-assign]
    scripted = ScriptedResearcher()

    async def check() -> None:
        context = cast(ServerRequestContext[Any], None)

        async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            result = await adapter.call_tool(
                context,
                types.CallToolRequestParams(
                    name=name,
                    arguments=arguments,
                ),
            )
            assert result.is_error is False
            first = result.content[0]
            assert isinstance(first, types.TextContent)
            return json.loads(first.text)

        plan = scripted.propose(started["model_context"])
        staged = await call(
            "submit_algorithm_plan",
            {
                "session_id": started["session_id"],
                "checkpoint_token": started["checkpoint_token"],
                "plan": plan,
                "response_mode": "compact",
            },
        )
        assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
        assert staged["continuation"]["required_model_action"] == "AUTHOR_AND_SUBMIT_DIAGNOSIS"
        assert staged["model_context"]["schema"] == "research-diagnostic-context-v1"
        assert staged["completed_generations"] == 0
        assert staged["history"] == []
        diagnosis = scripted.propose(staged["model_context"])
        finished = await call(
            "submit_algorithm_diagnosis",
            {
                "session_id": started["session_id"],
                "checkpoint_token": staged["checkpoint_token"],
                "diagnosis": diagnosis,
                "response_mode": "compact",
            },
        )
        assert finished["completed_generations"] == 1
        assert finished["checkpoint_phase"] == "AWAITING_PLAN"
        assert finished["continuation"]["required_model_action"] == "AUTHOR_AND_SUBMIT_PLAN"
        assert len(finished["history"]) == 1
        authoritative = server._dispatch(
            "get_algorithm_research",
            {
                "session_id": started["session_id"],
            },
        )
        assert finished["checkpoint_token"] == authoritative["checkpoint_token"]
        assert (
            finished["last_completed_evidence_hash"]
            == authoritative["history"][-1]["evidence_hash"]
        )
        assert authoritative["completed_generations"] == 1

    asyncio.run(check())


def test_after_successful_write_compact_failure_never_returns_false_execution_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.chatgpt_mcp_sdk as direct

    server, started = _setup(tmp_path)
    adapter = create_chatgpt_sdk_adapter(state_dir=tmp_path / "adapter", project_root=tmp_path)
    adapter.dispatcher._dispatch = server._dispatch  # type: ignore[method-assign]

    def impossible(_payload: dict[str, Any]) -> dict[str, Any]:
        raise ChatCheckpointCompressionError("oversized synthetic fixture")

    monkeypatch.setattr(direct, "compact_academic_checkpoint", impossible)

    async def check() -> None:
        result = await adapter.call_tool(
            cast(ServerRequestContext[Any], None),
            types.CallToolRequestParams(
                name="submit_algorithm_plan",
                arguments={
                    "session_id": started["session_id"],
                    "checkpoint_token": started["checkpoint_token"],
                    "plan": ScriptedResearcher().propose(started["model_context"]),
                    "response_mode": "compact",
                },
            ),
        )
        assert result.is_error is False  # committed successfully, never misreport ERROR
        data = json.loads(cast(types.TextContent, result.content[0]).text)
        assert data["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
        assert data["compact_submission_status"] == "FULL_FALLBACK_AFTER_SUCCESSFUL_WRITE"
        assert data["completed_generations"] == 0
        authoritative = server._dispatch(
            "get_algorithm_research",
            {
                "session_id": started["session_id"],
            },
        )
        assert authoritative["checkpoint_phase"] == "AWAITING_DIAGNOSIS"

    asyncio.run(check())
