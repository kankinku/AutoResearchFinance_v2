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
        "initialize_research_state",
        "get_workspace_status",
        "validate_strategy",
        "import_strategies",
        "list_strategies",
        "list_features",
        "get_dashboard_status",
        "get_research_evidence",
        "run_evaluation",
        "check_system",
        "start_system",
        "get_system_status",
        "stop_system",
    }
    assert not any(
        forbidden in name
        for name in names
        for forbidden in ("order", "credential", "promote", "live", "direct_edit")
    )


def test_mcp_evaluation_defaults_match_research_policy(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path, project_root=tmp_path)
    response = _call(server, {"jsonrpc": "2.0", "id": 9, "method": "tools/list"})
    result = response["result"]
    assert isinstance(result, dict)
    tools = result["tools"]
    assert isinstance(tools, list)
    evaluation = next(tool for tool in tools if tool["name"] == "run_evaluation")
    schema = evaluation["inputSchema"]
    assert schema["properties"]["min_annual_trades"]["default"] == 30
    assert schema["properties"]["min_qqq_cagr_delta"]["default"] == 0.10


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
    assert context["failure_knowledge"] == []
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
    accepted_payload = _text(accepted)
    assert accepted_payload["status"] == "VALIDATED"
    assert accepted_payload["_compatibility"] == {
        "status": "DEPRECATED",
        "replacement_tools": [
            "start_system",
            "run_evaluation",
            "validate_strategy",
            "get_system_status",
        ],
        "note": (
            "This tool only validates and records an intent; it does not execute "
            "research. Use start_system for managed research or run_evaluation "
            "for one-shot evaluation."
        ),
    }
    intent_path = tmp_path / "llm" / "intents.jsonl"
    assert intent_path.is_file()
    persisted = intent_path.read_text(encoding="utf-8")
    assert "_compatibility" not in persisted
    assert "DEPRECATED" not in persisted

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



def _write_phase4_strategy(root: Path) -> None:
    (root / "strategy.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "phase4-mcp",
                "family": "trend",
                "generation": 0,
                "indicators": {"fast": {"type": "SMA", "period": 5}},
                "entry": {
                    "logic": "AND",
                    "conditions": [
                        {"op": "greater_than", "left": "close", "value": 0}
                    ],
                },
                "exit": {
                    "logic": "AND",
                    "conditions": [
                        {"op": "less_than", "left": "close", "value": 0}
                    ],
                },
                "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
            }
        ),
        encoding="utf-8",
    )


def test_phase4_mcp_workspace_strategy_and_planning_tools_are_safe(tmp_path: Path) -> None:
    _write_phase4_strategy(tmp_path)
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)

    initialized = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "name": "initialize_research_state",
                    "arguments": {},
                },
            },
        )
    )
    assert initialized["status"] == "INITIALIZED"
    assert initialized["orders_enabled"] is False

    workspace = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {"name": "get_workspace_status", "arguments": {}},
            },
        )
    )
    assert workspace["status"] == "READY"
    assert workspace["orders_enabled"] is False

    mode = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 211,
                "method": "tools/call",
                "params": {
                    "name": "set_research_mode",
                    "arguments": {"mode": "live"},
                },
            },
        )
    )
    assert mode["status"] == "MODE_SELECTED"
    assert mode["selected_mode"] == "live"
    assert mode["orders_enabled"] is False

    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "valid.json").write_text(
        json.dumps({"experiment_hash": "hash-1"}),
        encoding="utf-8",
    )
    cache = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 212,
                "method": "tools/call",
                "params": {
                    "name": "validate_research_cache",
                    "arguments": {},
                },
            },
        )
    )
    assert cache["status"] == "VALIDATED"
    assert cache["validated_manifests"] == 1
    assert cache["orders_enabled"] is False

    validated = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "tools/call",
                "params": {
                    "name": "validate_strategy",
                    "arguments": {"source_path": "strategy.json"},
                },
            },
        )
    )
    assert validated["status"] == "VALID"
    assert validated["strategy_id"] == "phase4-mcp"

    imported = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 23,
                "method": "tools/call",
                "params": {
                    "name": "import_strategies",
                    "arguments": {"source_path": "strategy.json"},
                },
            },
        )
    )
    assert imported["status"] == "DRY_RUN"
    assert imported["orders_enabled"] is False
    assert not (tmp_path / "strategies" / "catalog.json").exists()

    planned = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 24,
                "method": "tools/call",
                "params": {
                    "name": "plan_generation",
                    "arguments": {
                        "parent_ids": ["phase4-mcp"],
                        "method": "random",
                        "count": 8,
                        "seed": 3,
                    },
                },
            },
        )
    )
    assert planned["parent_ids"] == ["phase4-mcp"]
    assert planned["method"] == "random"
    assert planned["count"] == 8
    assert planned["seed"] == 3


def test_phase4_mcp_strategy_tools_reject_project_escape_and_unsafe_repository(
    tmp_path: Path,
) -> None:
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    escaped = _call(
        server,
        {
            "jsonrpc": "2.0",
            "id": 25,
            "method": "tools/call",
            "params": {
                "name": "validate_strategy",
                "arguments": {"source_path": str(outside)},
            },
        },
    )
    escaped_result = escaped["result"]
    assert isinstance(escaped_result, dict)
    assert escaped_result["isError"] is True
    assert str(outside) not in str(escaped)

    unsafe_repo = _call(
        server,
        {
            "jsonrpc": "2.0",
            "id": 26,
            "method": "tools/call",
            "params": {
                "name": "import_strategies",
                "arguments": {"repository_url": "http://example.com/repo.git"},
            },
        },
    )
    unsafe_result = unsafe_repo["result"]
    assert isinstance(unsafe_result, dict)
    assert unsafe_result["isError"] is True
    assert "example.com" not in str(unsafe_repo)



def test_submit_research_intent_is_hidden_but_legacy_direct_call_still_works(
    tmp_path: Path,
) -> None:
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)

    response = _call(server, {"jsonrpc": "2.0", "id": 40, "method": "tools/list"})
    result = response["result"]
    assert isinstance(result, dict)
    tools = result["tools"]
    assert isinstance(tools, list)
    names = {
        str(tool["name"])
        for tool in tools
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }
    assert "submit_research_intent" not in names

    valid = {
        "mode": "structure",
        "parent_ids": ["champion-1"],
        "operations": [],
        "rationale": "legacy compatibility",
    }
    payload = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {"name": "submit_research_intent", "arguments": valid},
            },
        )
    )
    assert payload["status"] == "VALIDATED"
    assert payload["_compatibility"]["status"] == "DEPRECATED"


def test_hidden_legacy_internal_tools_remain_directly_callable_with_migration_metadata(
    tmp_path: Path,
) -> None:
    _write_phase4_strategy(tmp_path)
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)

    calls = (
        ("set_research_mode", {"mode": "paper"}, "get_workspace_status"),
        ("validate_research_cache", {}, None),
        (
            "plan_generation",
            {
                "parent_ids": ["phase4-mcp"],
                "method": "random",
                "count": 2,
                "seed": 1,
            },
            "start_system",
        ),
        ("get_research_context", {}, "list_features"),
    )
    for index, (name, arguments, expected_replacement) in enumerate(calls, start=50):
        payload = _text(
            _call(
                server,
                {
                    "jsonrpc": "2.0",
                    "id": index,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
        )
        compatibility = payload["_compatibility"]
        assert compatibility["status"] == "LEGACY_INTERNAL_TOOL"
        replacements = compatibility["replacement_tools"]
        assert isinstance(replacements, list)
        if expected_replacement is None:
            assert replacements == []
        else:
            assert expected_replacement in replacements



def test_public_mcp_responses_include_versioned_contract_metadata(tmp_path: Path) -> None:
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)

    initialized = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 70,
                "method": "tools/call",
                "params": {"name": "initialize_research_state", "arguments": {}},
            },
        )
    )
    features = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 71,
                "method": "tools/call",
                "params": {"name": "list_features", "arguments": {}},
            },
        )
    )
    system = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 72,
                "method": "tools/call",
                "params": {"name": "get_system_status", "arguments": {}},
            },
        )
    )
    preflight = _text(
        _call(
            server,
            {
                "jsonrpc": "2.0",
                "id": 73,
                "method": "tools/call",
                "params": {
                    "name": "check_system",
                    "arguments": {
                        "source_path": "missing.json",
                        "data_path": "missing.parquet",
                    },
                },
            },
        )
    )

    assert initialized["_contract"]["plane"] == "BOOTSTRAP_CONFIGURATION"
    assert features["_contract"]["plane"] == "CATALOG_VALIDATION"
    assert system["_contract"]["plane"] == "EVIDENCE_STATUS"
    assert preflight["_contract"]["plane"] == "EXECUTION_LIFECYCLE"

    for payload in (initialized, features, system, preflight):
        contract = payload["_contract"]
        assert contract["schema_version"] == 1
        assert contract["orders_enabled"] is False
        assert isinstance(contract["tool"], str)
