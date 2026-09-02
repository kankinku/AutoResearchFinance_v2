from __future__ import annotations

import json
from pathlib import Path

from integrations.codex_mcp_server import create_mcp_server


def _call(server: object, request: dict[str, object]) -> dict[str, object]:
    response = server.handle(request)  # type: ignore[attr-defined]
    assert isinstance(response, dict)
    return response


def _text(response: dict[str, object]) -> dict[str, object]:
    result = response["result"]
    assert isinstance(result, dict)
    content = result["content"]
    assert isinstance(content, list)
    item = content[0]
    assert isinstance(item, dict)
    return json.loads(str(item["text"]))


def test_mcp_server_lists_only_safe_research_tools(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)

    response = _call(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    result = response["result"]
    assert isinstance(result, dict)
    tools = result["tools"]
    assert isinstance(tools, list)
    names = {str(tool["name"]) for tool in tools if isinstance(tool, dict)}
    assert names == {
        "get_research_context",
        "list_features",
        "get_dashboard_status",
        "submit_research_intent",
        "run_evaluation",
        "check_system",
        "start_system",
        "get_system_status",
        "stop_system",
    }
    assert not any("order" in name or "credential" in name for name in names)


def test_mcp_server_returns_context_and_features_without_raw_data(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)

    context = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_research_context", "arguments": {}},
            },
        )
    )
    features = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_features", "arguments": {}},
            },
        )
    )

    assert "raw_market_rows" not in context
    assert "sealed_oos" not in context
    assert context["feature_catalog"]
    assert isinstance(features["features"], list)


def test_mcp_server_exposes_full_registered_feature_catalog(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)

    features = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "list_features", "arguments": {}},
            },
        )
    )

    catalog = features["features"]
    assert isinstance(catalog, list)
    assert len(catalog) == 173
    assert any(item.get("name") == "rsi" for item in catalog if isinstance(item, dict))
    assert any(
        item.get("name") == "us_20y_change" for item in catalog if isinstance(item, dict)
    )


def test_mcp_server_validates_and_records_intent_but_rejects_code_changes(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)
    valid = {
        "mode": "structure",
        "parent_ids": ["champion-1"],
        "operations": [],
        "rationale": "compare momentum and volatility",
    }

    accepted = _call(
        server,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "submit_research_intent", "arguments": valid},
        },
    )
    assert _text(accepted)["status"] == "VALIDATED"
    assert (tmp_path / "llm" / "intents.jsonl").is_file()

    rejected = _call(
        server,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "submit_research_intent",
                "arguments": {**valid, "python_patch": "danger"},
            },
        },
    )
    result = rejected["result"]
    assert isinstance(result, dict)
    assert result["isError"] is True
    assert "danger" not in str(rejected)


def test_mcp_server_handles_notifications_and_invalid_requests(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)

    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    response = _call(server, {"jsonrpc": "2.0", "id": 6, "method": "unknown"})
    assert response["error"]


def test_mcp_system_preflight_returns_actionable_blockers_without_starting(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)

    response = _call(
        server,
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "start_system",
                "arguments": {
                    "source_path": "strategies/missing.py",
                    "data_path": "data/missing.parquet",
                },
            },
        },
    )

    payload = _text(response)
    assert payload["status"] == "BLOCKED"
    assert payload["preflight"]["issues"]
    assert "Docker" in str(payload["preflight"]["checks"])
