from __future__ import annotations

import json
from pathlib import Path

from integrations.codex_mcp_server import _tools

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


def test_phase3_6_2_target_partition_covers_current_18_tool_surface() -> None:
    current = {
        str(tool["name"])
        for tool in _tools()
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

    assert len(current) == 18
    assert removed == EXPECTED_REMOVED
    assert EXPECTED_TARGET | EXPECTED_REMOVED == current
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


def test_phase3_6_2_does_not_change_current_tools_list_yet() -> None:
    names = {
        str(tool["name"])
        for tool in _tools()
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }

    assert len(names) == 18
    assert EXPECTED_TARGET < names
    assert EXPECTED_REMOVED < names



def test_phase3_6_3_soft_deprecation_keeps_18_tools_and_original_intent_schema() -> None:
    tools = _tools()
    by_name = {str(tool["name"]): tool for tool in tools}

    assert len(by_name) == 18
    intent_tool = by_name["submit_research_intent"]
    assert str(intent_tool["description"]).startswith("[DEPRECATED]")
    assert set(intent_tool) == {"name", "description", "inputSchema"}
