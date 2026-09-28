from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from application.services import create_application_services
from integrations.codex_mcp_server import _PUBLIC_TOOL_PLANES, _all_tools, _tools

EXPECTED_PUBLIC = {
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

EXPECTED_LEGACY = {
    "set_research_mode",
    "validate_research_cache",
    "plan_generation",
    "get_research_context",
    "submit_research_intent",
}


def test_phase3_6_public_and_legacy_surfaces_are_finalized() -> None:
    public = {
        str(tool["name"])
        for tool in _tools()
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }
    all_names = {
        str(tool["name"])
        for tool in _all_tools()
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }

    assert public == EXPECTED_PUBLIC
    assert len(public) == 13
    assert EXPECTED_LEGACY.isdisjoint(public)
    assert all_names == EXPECTED_PUBLIC | EXPECTED_LEGACY
    assert set(_PUBLIC_TOOL_PLANES) == EXPECTED_PUBLIC
    assert not any("order" in name or "live" in name for name in public)


def test_phase3_6_internalized_capabilities_remain_available_in_application_services(
    tmp_path: Path,
) -> None:
    services = create_application_services(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    assert callable(services.workspace.set_mode)
    assert callable(services.workspace.validate_cache)
    assert callable(services.planning.plan_generation)
    assert callable(services.research.context)
    assert callable(services.research.validate_and_record_intent)


def test_phase3_6_internalized_capabilities_remain_available_in_cli() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, str(root / "cli.py"), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    for command in ("set-mode", "rebuild-cache", "plan-generation", "research-intent"):
        assert command in completed.stdout
