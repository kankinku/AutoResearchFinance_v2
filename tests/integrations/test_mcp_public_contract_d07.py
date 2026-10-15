"""D07: every advertised tool must be schema-checked before side effects."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from mcp import types
from mcp.server import ServerRequestContext

from integrations.chatgpt_mcp_sdk import chatgpt_tools, create_chatgpt_sdk_adapter


def _example(schema: dict[str, Any]) -> object:
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    if "anyOf" in schema:
        return _example(schema["anyOf"][0])
    typ = schema.get("type", "object")
    if typ == "string":
        if schema.get("format") == "date":
            return "2026-10-14"
        if schema.get("pattern") == "^[0-9a-f]{32}$":
            return "a" * 32
        return "development"
    if typ == "integer":
        return max(1, schema.get("minimum", 0))
    if typ == "number":
        return max(1.0, schema.get("minimum", 0))
    if typ == "boolean":
        return False
    if typ == "array":
        return [_example(schema["items"]) for _ in range(schema.get("minItems", 0))]
    if typ == "object":
        required = list(schema.get("required", []))
        if "oneOf" in schema:
            # import_strategies: exactly one of a local path or a repository URI.
            required.extend(schema["oneOf"][0].get("required", []))
        return {
            k: _example(schema["properties"][k]) for k in dict.fromkeys(required)
        }
    raise AssertionError(f"unhandled schema element: {schema}")


def test_every_public_schema_and_plane_is_coherent() -> None:
    advertised = chatgpt_tools()
    assert len(advertised) == 32
    names = [str(tool["name"]) for tool in advertised]
    assert len(names) == len(set(names))
    assert {"start_algorithm_research", "submit_algorithm_plan",
            "submit_algorithm_diagnosis", "evaluate_algorithm_experiments"} <= set(names)
    assert all(not any(unsafe in name for unsafe in (
        "order", "credential", "start_system", "stop_system",
        "code_execute", "shell", "write_file",
    )) for name in names)
    for t in advertised:
        schema = t["inputSchema"]
        assert schema["type"] == "object", t["name"]
        Draft202012Validator.check_schema(schema)
        assert schema.get("additionalProperties") is False, t["name"]
        args = _example(schema)
        assert isinstance(args, dict)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(args)


def test_all_32_valid_calls_route_exactly_once_with_public_contract(tmp_path: Path) -> None:
    adapter = create_chatgpt_sdk_adapter(
        project_root=tmp_path, state_dir=tmp_path / "state",
    )
    invocations: list[tuple[str, dict]] = []

    def sandbox_dispatch(name: str, arguments: dict) -> dict:
        invocations.append((name, arguments))
        return {"status": "D07_ISOLATED_DISPATCH", "orders_enabled": False}

    adapter.dispatcher._dispatch = sandbox_dispatch  # type: ignore[method-assign]

    async def verify() -> None:
        ctx = cast(ServerRequestContext[Any], None)
        for item in chatgpt_tools():
            name = item["name"]
            arguments = _example(item["inputSchema"])
            answer = await adapter.call_tool(
                ctx, types.CallToolRequestParams(name=name, arguments=arguments)
            )
            assert answer.is_error is False, name
            assert isinstance(answer.content[0], types.TextContent)
            result = json.loads(answer.content[0].text)
            assert result["orders_enabled"] is False
            assert result["_contract"]["orders_enabled"] is False
            assert result["_contract"]["tool"] == name
            assert invocations[-1] == (name, arguments)
        assert len(invocations) == 32
        assert {name for name, _ in invocations} == {
            tool["name"] for tool in chatgpt_tools()
        }

    asyncio.run(verify())


def test_all_32_unknown_fields_rejected_before_any_dispatch(tmp_path: Path) -> None:
    adapter = create_chatgpt_sdk_adapter(
        project_root=tmp_path, state_dir=tmp_path / "state",
    )
    calls: list[str] = []

    def forbidden(name: str, arguments: dict) -> None:
        calls.append(name)
        raise AssertionError("invalid external MCP input crossed dispatch boundary")

    adapter.dispatcher._dispatch = forbidden  # type: ignore[method-assign]

    async def verify() -> None:
        ctx = cast(ServerRequestContext[Any], None)
        for item in chatgpt_tools():
            arguments = _example(item["inputSchema"])
            assert isinstance(arguments, dict)
            arguments["__unexpected_runtime_order__"] = "BUY_NOW"
            response = await adapter.call_tool(
                ctx, types.CallToolRequestParams(name=item["name"], arguments=arguments)
            )
            assert response.is_error is True, item["name"]
            assert isinstance(response.content[0], types.TextContent)
            body = json.loads(response.content[0].text)
            assert body["error_code"] == "INVALID_TOOL_ARGUMENTS", item["name"]
            assert body["orders_enabled"] is False
        assert calls == []

    asyncio.run(verify())


def test_required_fields_and_typed_boundaries_are_not_dispatched(tmp_path: Path) -> None:
    adapter = create_chatgpt_sdk_adapter(
        project_root=tmp_path, state_dir=tmp_path / "state",
    )
    called = []
    adapter.dispatcher._dispatch = (  # type: ignore[method-assign]
        lambda name, args: called.append(name)
    )

    async def verify() -> None:
        ctx = cast(ServerRequestContext[Any], None)
        for item in chatgpt_tools():
            schema = item["inputSchema"]
            for required in schema.get("required", []):
                args = _example(schema)
                assert isinstance(args, dict)
                args.pop(required)
                response = await adapter.call_tool(
                    ctx, types.CallToolRequestParams(name=item["name"], arguments=args)
                )
                assert response.is_error is True, (item["name"], required)
        cases = [
            ("start_algorithm_research", {"data_path": "study.parquet", "generations": 101}),
            ("start_algorithm_research", {"data_path": "study.parquet", "generations": True}),
            ("submit_algorithm_plan", {
                "session_id": "bad", "checkpoint_token": "a"*32, "plan": {},
            }),
            ("submit_algorithm_diagnosis", {
                "session_id": "a"*32, "checkpoint_token": "a"*32,
                "diagnosis": {}, "require_signal_change": "true",
            }),
            ("download_market_data", {
                "provider": "evil", "symbol": "QQQ",
                "start": "2026-09-01", "end": "2026-09-02",
            }),
            ("download_market_data", {
                "provider": "tiingo", "symbol": "QQQ",
                "start": "2026-99-99", "end": "2026-09-02",
            }),
            ("submit_guided_generation", {
                "session_id": "a"*32, "checkpoint_token": "a"*32,
                "generation": 0, "source_path": "test.yml", "intent": {},
            }),
        ]
        for name, args in cases:
            response = await adapter.call_tool(
                ctx, types.CallToolRequestParams(name=name, arguments=args)
            )
            assert response.is_error is True, name
            content = response.content[0]
            assert isinstance(content, types.TextContent)
            assert json.loads(content.text)["error_code"] == "INVALID_TOOL_ARGUMENTS"
        assert called == []

    asyncio.run(verify())


def test_unknown_tool_stays_blocked(tmp_path: Path) -> None:
    adapter = create_chatgpt_sdk_adapter(project_root=tmp_path, state_dir=tmp_path/"state")
    async def verify() -> None:
        result = await adapter.call_tool(
            cast(ServerRequestContext[Any], None),
            types.CallToolRequestParams(name="start_system", arguments={}),
        )
        assert result.is_error is True
        assert isinstance(result.content[0], types.TextContent)
        assert json.loads(result.content[0].text)["status"] == "ERROR"
    asyncio.run(verify())
