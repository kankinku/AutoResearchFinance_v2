from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "operations" / "mcp-phase6-1-post-cutover-inventory.json"
DESIGN = ROOT / "docs" / "operations" / "mcp-phase6-1-post-cutover-stabilization.md"


def test_phase6_1_inventory_captures_current_transport_dependencies() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert payload["phase"] == "6.1"
    assert payload["canonical"]["transport"] == "official_sdk"
    assert payload["canonical"]["entrypoint"] == "integrations.codex_mcp_server"
    assert payload["rollback"]["entrypoint"] == "integrations.codex_mcp_manual_server"
    assert payload["rollback"]["protocol_version"] == "2024-11-05"

    debts = payload["technical_debt"]
    assert debts["sdk_imports_legacy_protocol_for_text_content"] is True
    assert debts["shared_core_contains_manual_jsonrpc_handle"] is True
    assert debts["shared_core_imports_legacy_protocol_helpers"] is True
    assert debts["hidden_legacy_tool_dispatch_is_separate_from_transport_rollback"] is True


def test_phase6_1_stabilization_plan_does_not_delete_rollback_or_hidden_dispatch() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert payload["non_goals"] == [
        "delete_manual_rollback_transport",
        "delete_hidden_legacy_tool_dispatch",
        "change_public_tool_surface",
        "change_application_services",
        "change_finance_or_strategy_logic",
        "change_order_permissions",
    ]
    assert payload["contracts"]["public_tools"] == 13
    assert payload["contracts"]["hidden_legacy_dispatch"] == 5
    assert payload["contracts"]["orders_enabled"] is False


def test_phase6_1_design_freezes_decoupling_sequence() -> None:
    text = DESIGN.read_text(encoding="utf-8")

    for marker in (
        "Phase 6.2",
        "Phase 6.3",
        "Phase 6.4",
        "neutral payload codec",
        "manual JSON-RPC ownership",
        "13 public",
        "5 hidden legacy",
        "orders_enabled=false",
        "codex_mcp_protocol.py",
    ):
        assert marker in text
