from __future__ import annotations

import json
from pathlib import Path

from integrations.codex_mcp_server import (
    _PUBLIC_TOOL_PLANES,
    _all_tools,
    _tools,
    _with_public_contract,
)

INVENTORY_PATH = Path("docs/operations/mcp-phase3-6-1-tool-inventory.json")
TARGET_PATH = Path("docs/operations/mcp-phase3-6-2-target-surface.json")

EXPECTED_TARGET = {
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

EXPECTED_REMOVED = {
    "set_research_mode",
    "validate_research_cache",
    "plan_generation",
    "get_research_context",
    "submit_research_intent",
}


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_phase3_6_2_target_surface_has_exact_13_long_term_tools() -> None:
    payload = _load(TARGET_PATH)
    target = payload["target_public_tools"]

    assert isinstance(target, list)
    assert len(target) == 13
    assert set(target) == EXPECTED_TARGET
    assert payload["target_public_tool_count"] == 13
    assert payload["workspace_status_decision"] == (
        "KEEP_AS_BOOTSTRAP_CONFIGURATION_PLANE"
    )


def test_phase3_6_2_target_partition_covers_legacy_18_tool_surface() -> None:
    legacy = {
        str(tool["name"])
        for tool in _all_tools()
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }
    target = _load(TARGET_PATH)
    removed_records = target["removed_from_default_public_surface"]
    assert isinstance(removed_records, list)
    removed = {
        str(record["name"])
        for record in removed_records
        if isinstance(record, dict) and isinstance(record.get("name"), str)
    }

    assert len(legacy) == 18
    assert removed == EXPECTED_REMOVED
    assert EXPECTED_TARGET | EXPECTED_REMOVED == legacy
    assert EXPECTED_TARGET.isdisjoint(EXPECTED_REMOVED)


def test_phase3_6_2_target_preserves_all_phase3_6_1_public_keep_tools() -> None:
    inventory = _load(INVENTORY_PATH)
    records = inventory["tools"]
    assert isinstance(records, list)
    public_keep = {
        str(record["name"])
        for record in records
        if isinstance(record, dict) and record.get("classification") == "PUBLIC_KEEP"
    }

    assert public_keep <= EXPECTED_TARGET
    assert EXPECTED_TARGET - public_keep == {"get_workspace_status"}


def test_phase3_6_2_removed_tools_follow_inventory_dispositions() -> None:
    inventory = _load(INVENTORY_PATH)
    records = inventory["tools"]
    assert isinstance(records, list)
    by_name = {
        str(record["name"]): record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("name"), str)
    }

    target = _load(TARGET_PATH)
    removed_records = target["removed_from_default_public_surface"]
    assert isinstance(removed_records, list)
    removed = {
        str(record["name"]): record
        for record in removed_records
        if isinstance(record, dict) and isinstance(record.get("name"), str)
    }

    assert removed["submit_research_intent"]["disposition"] == "DEPRECATE"
    assert by_name["submit_research_intent"]["classification"] == (
        "DEPRECATE_CANDIDATE"
    )

    for name in EXPECTED_REMOVED - {"submit_research_intent"}:
        assert removed[name]["disposition"] == "INTERNALIZE"
        assert by_name[name]["classification"] == "INTERNALIZE_CANDIDATE"


def test_phase3_6_2_compatibility_policy_avoids_alias_sprawl_and_hard_removal() -> None:
    payload = _load(TARGET_PATH)
    compatibility = payload["compatibility_policy"]
    assert isinstance(compatibility, dict)

    assert compatibility["add_new_aliases"] is False
    assert compatibility["add_custom_tool_schema_metadata"] is False
    assert compatibility["soft_deprecation_phase"] == "3-6.3"
    assert compatibility["target_tools_list_phase"] == "3-6.4"
    assert compatibility["legacy_dispatch_supported_through"] == "3-6.7"
    assert compatibility["hard_dispatch_removal"] == (
        "OUT_OF_PHASE_3_6_REQUIRES_EXPLICIT_LATER_APPROVAL"
    )
    assert compatibility["hidden_dispatch_is_security_boundary"] is False


def test_phase3_6_4_advertises_exact_target_13_tools() -> None:
    names = {
        str(tool["name"])
        for tool in _tools()
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }

    assert len(names) == 13
    assert names == EXPECTED_TARGET
    assert names.isdisjoint(EXPECTED_REMOVED)


def test_phase3_6_3_soft_deprecation_definition_remains_in_legacy_catalog() -> None:
    by_name = {str(tool["name"]): tool for tool in _all_tools()}

    assert len(by_name) == 18
    intent_tool = by_name["submit_research_intent"]
    assert str(intent_tool["description"]).startswith("[DEPRECATED]")
    assert set(intent_tool) == {"name", "description", "inputSchema"}



def test_phase3_6_5_workspace_status_is_explicit_bootstrap_configuration_tool() -> None:
    by_name = {str(tool["name"]): tool for tool in _tools()}
    workspace = by_name["get_workspace_status"]

    description = str(workspace["description"])
    assert "bootstrap/configuration" in description
    assert "get_system_status" in description
    assert "get_dashboard_status" in description
    assert workspace["inputSchema"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }



def test_phase3_6_6_public_response_contract_covers_exact_13_tools() -> None:
    assert set(_PUBLIC_TOOL_PLANES) == EXPECTED_TARGET
    assert set(_PUBLIC_TOOL_PLANES.values()) == {
        "BOOTSTRAP_CONFIGURATION",
        "CATALOG_VALIDATION",
        "EVIDENCE_STATUS",
        "EXECUTION_LIFECYCLE",
    }


def test_phase3_6_6_public_response_contract_is_additive_and_versioned() -> None:
    for name, plane in _PUBLIC_TOOL_PLANES.items():
        original = {"status": "OK", "existing": {"preserved": True}}
        payload = _with_public_contract(name, original)

        assert isinstance(payload, dict)
        assert payload["status"] == "OK"
        assert payload["existing"] == {"preserved": True}
        assert payload["_contract"] == {
            "schema_version": 1,
            "tool": name,
            "plane": plane,
            "orders_enabled": False,
        }


def test_phase3_6_6_legacy_responses_do_not_receive_public_contract_metadata() -> None:
    for name in EXPECTED_REMOVED:
        payload = _with_public_contract(name, {"status": "OK"})
        assert payload == {"status": "OK"}
