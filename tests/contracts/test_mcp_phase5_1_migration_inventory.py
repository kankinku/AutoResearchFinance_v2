from __future__ import annotations

import json
from pathlib import Path

from integrations.codex_mcp_server import _all_tools, _tools

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "operations" / "mcp-phase5-1-sdk-migration-inventory.json"
DESIGN = ROOT / "docs" / "operations" / "mcp-phase5-1-sdk-migration-design.md"

PUBLIC_TOOLS = {
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

LEGACY_TOOLS = {
    "set_research_mode",
    "validate_research_cache",
    "plan_generation",
    "get_research_context",
    "submit_research_intent",
}


def _tool_names(tools: list[dict[str, object]]) -> set[str]:
    return {
        str(tool["name"])
        for tool in tools
        if isinstance(tool.get("name"), str)
    }


def test_phase5_1_inventory_matches_current_mcp_surface() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert payload["phase"] == "5.1"
    assert payload["current_transport"]["kind"] == "manual_stdio_jsonrpc"
    assert payload["current_transport"]["protocol_version"] == "2024-11-05"
    assert set(payload["contracts"]["public_tools"]) == PUBLIC_TOOLS
    assert set(payload["contracts"]["hidden_legacy_tools"]) == LEGACY_TOOLS
    assert _tool_names(_tools()) == PUBLIC_TOOLS
    assert _tool_names(_all_tools()) == PUBLIC_TOOLS | LEGACY_TOOLS


def test_phase5_1_target_uses_official_v2_low_level_sdk_without_surface_expansion() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    target = payload["target_sdk"]

    assert target["package"] == "mcp"
    assert target["version_constraint"] == "mcp>=2.2,<3"
    assert target["server_api"] == "mcp.server.Server"
    assert target["transport"] == "stdio"
    assert target["migration_mode"] == "parallel_adapter_then_cutover"
    assert payload["contracts"]["orders_enabled"] is False
    assert payload["non_goals"] == [
        "add_order_tools",
        "add_live_account_tools",
        "remove_legacy_dispatch",
        "change_application_services",
        "change_strategy_or_finance_logic",
    ]


def test_phase5_1_design_freezes_cutover_gates() -> None:
    text = DESIGN.read_text(encoding="utf-8")

    for marker in (
        "13 public",
        "5 hidden legacy",
        "mcp.server.Server",
        "mcp>=2.2,<3",
        "parallel adapter",
        "STDIO",
        "orders_enabled=false",
        "Phase 5.2",
        "Phase 5.3",
        "Phase 5.4",
        "Phase 5.5",
    ):
        assert marker in text
