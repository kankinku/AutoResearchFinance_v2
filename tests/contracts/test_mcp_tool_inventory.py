from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from integrations.codex_mcp_server import _all_tools

INVENTORY_PATH = Path("docs/operations/mcp-phase3-6-1-tool-inventory.json")
CLASSIFICATIONS = {
    "PUBLIC_KEEP",
    "DUPLICATE_OR_OVERLAP",
    "INTERNALIZE_CANDIDATE",
    "DEPRECATE_CANDIDATE",
}
EFFECTS = {
    "READ_ONLY",
    "READ_WITH_RECONCILIATION",
    "STATE_MUTATION",
    "EXECUTION_TRIGGER",
    "LIFECYCLE_CONTROL",
}


def _inventory() -> dict[str, object]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_phase3_6_1_inventory_covers_exact_public_mcp_surface() -> None:
    actual = {
        str(tool["name"])
        for tool in _all_tools()
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }
    payload = _inventory()
    records = payload["tools"]
    assert isinstance(records, list)
    inventoried = {
        str(record["name"])
        for record in records
        if isinstance(record, dict) and isinstance(record.get("name"), str)
    }

    assert len(records) == 18
    assert inventoried == actual


def test_phase3_6_1_inventory_uses_only_declared_classifications_and_effects() -> None:
    payload = _inventory()
    records = payload["tools"]
    assert isinstance(records, list)

    classifications = []
    for record in records:
        assert isinstance(record, dict)
        classification = record["classification"]
        effect = record["effect"]
        assert classification in CLASSIFICATIONS
        assert effect in EFFECTS
        assert isinstance(record.get("service"), str)
        assert isinstance(record.get("rationale"), str)
        assert isinstance(record.get("follow_up"), str)
        classifications.append(classification)

    counts = Counter(classifications)
    assert counts == {
        "PUBLIC_KEEP": 12,
        "DUPLICATE_OR_OVERLAP": 1,
        "INTERNALIZE_CANDIDATE": 4,
        "DEPRECATE_CANDIDATE": 1,
    }

    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["tool_count"] == 18
    for name, count in counts.items():
        assert summary[name] == count


def test_phase3_6_1_inventory_identifies_only_current_dead_end_as_deprecate_candidate() -> None:
    payload = _inventory()
    records = payload["tools"]
    assert isinstance(records, list)

    deprecated = [
        str(record["name"])
        for record in records
        if isinstance(record, dict)
        and record.get("classification") == "DEPRECATE_CANDIDATE"
    ]

    assert deprecated == ["submit_research_intent"]


def test_phase3_6_1_does_not_change_tool_names_or_input_schemas() -> None:
    by_name = {str(tool["name"]): tool for tool in _all_tools()}

    assert set(by_name) == {
        "initialize_research_state",
        "get_workspace_status",
        "set_research_mode",
        "validate_research_cache",
        "validate_strategy",
        "import_strategies",
        "list_strategies",
        "plan_generation",
        "get_research_context",
        "list_features",
        "get_research_evidence",
        "get_dashboard_status",
        "submit_research_intent",
        "run_evaluation",
        "check_system",
        "start_system",
        "get_system_status",
        "stop_system",
    }
    assert all(isinstance(tool.get("inputSchema"), dict) for tool in by_name.values())
