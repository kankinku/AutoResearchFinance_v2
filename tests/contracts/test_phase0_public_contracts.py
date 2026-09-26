from __future__ import annotations

import argparse
from pathlib import Path

from cli import build_parser
from dashboard.app import create_app
from dashboard.service import DashboardService
from integrations.codex_mcp_server import _tools, create_mcp_server
from orchestration.evaluation_runner import run_local_evaluation
from orchestration.generation import CANONICAL_STAGES
from research.llm.codex_schema import research_intent_schema
from runtime.research_loop import run_autoresearch
from strategy_ir.schema import StrategyIR

EXPECTED_CLI_COMMANDS = {
    "audit",
    "autoresearch",
    "dashboard",
    "dashboard-refresh",
    "dashboard-status",
    "import-strategies",
    "import-strategy",
    "init",
    "list-features",
    "mode",
    "paper-order-smoke",
    "plan-generation",
    "promote-paper",
    "rebuild-cache",
    "repeat-research",
    "request-live-approval",
    "research-evidence",
    "research-intent",
    "resume",
    "run-generation",
    "set-mode",
    "status",
    "terminal",
    "validate-strategy",
}

BASELINE_MCP_TOOLS = {
    "get_research_context",
    "list_features",
    "get_dashboard_status",
    "get_research_evidence",
    "submit_research_intent",
    "run_evaluation",
    "check_system",
    "start_system",
    "get_system_status",
    "stop_system",
}

PHASE4_MCP_TOOLS = {
    "initialize_research_state",
    "get_workspace_status",
    "set_research_mode",
    "validate_research_cache",
    "validate_strategy",
    "import_strategies",
    "list_strategies",
    "plan_generation",
}

EXPECTED_DASHBOARD_ROUTES = {
    ("GET", "/"),
    ("GET", "/backtest"),
    ("GET", "/api/health"),
    ("GET", "/api/dashboard"),
    ("GET", "/api/features/catalog"),
    ("GET", "/api/strategies/catalog"),
    ("GET", "/api/research-evidence"),
    ("GET", "/api/backtest"),
    ("GET", "/api/backtest/runs/{run_id}"),
    ("POST", "/api/refresh"),
}

EXPECTED_STRATEGY_FIELDS = {
    "schema_version": (None, True),
    "strategy_id": ("id", True),
    "family": (None, True),
    "generation": (None, True),
    "parents": (None, False),
    "indicators": (None, True),
    "features": (None, False),
    "entry": (None, True),
    "exit": (None, True),
    "regime_filters": (None, False),
    "risk": (None, True),
    "research": (None, False),
    "provenance": (None, False),
}

EXPECTED_CANONICAL_STAGES = (
    "load_champion_frontier",
    "load_knowledge",
    "llm_research_direction",
    "local_experiment_planning",
    "candidate_generation",
    "cache_check",
    "strategy_mutation",
    "strategy_validation",
    "parallel_fast_backtest",
    "hard_gate",
    "parallel_full_backtest",
    "robustness_validation",
    "local_statistical_analysis",
    "robust_score",
    "state_update",
    "experiment_db_save",
    "knowledge_extraction",
    "llm_context_compression",
    "plateau_detection",
    "next_generation",
)


def _subparser_choices(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("CLI subparser action is missing")


def test_phase0_cli_command_surface_is_frozen() -> None:
    assert _subparser_choices(build_parser()) == EXPECTED_CLI_COMMANDS


def test_phase0_mcp_tool_surface_is_frozen() -> None:
    tools = _tools()
    by_name = {str(tool["name"]): tool for tool in tools}
    assert BASELINE_MCP_TOOLS.issubset(by_name)
    assert set(by_name) == BASELINE_MCP_TOOLS | PHASE4_MCP_TOOLS

    empty_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    for name in (
        "get_research_context",
        "list_features",
        "get_dashboard_status",
        "get_system_status",
        "stop_system",
    ):
        assert by_name[name]["inputSchema"] == empty_schema

    assert by_name["get_research_evidence"]["inputSchema"] == {
        "type": "object",
        "properties": {"research_run_id": {"type": "string"}},
        "additionalProperties": False,
    }
    assert by_name["submit_research_intent"]["inputSchema"] == research_intent_schema()

    evaluation_schema = by_name["run_evaluation"]["inputSchema"]
    assert evaluation_schema["required"] == ["source_path", "data_path"]
    assert set(evaluation_schema["properties"]) == {
        "source_path",
        "data_path",
        "method",
        "count",
        "seed",
        "min_trades",
        "min_annual_trades",
        "parameter_domains",
        "series_data_path",
        "min_qqq_cagr_delta",
    }

    for name in ("check_system", "start_system"):
        schema = by_name[name]["inputSchema"]
        assert schema["required"] == ["source_path", "data_path"]
        assert set(schema["properties"]) == {
            "source_path",
            "data_path",
            "method",
            "count",
            "seed",
            "min_trades",
            "min_annual_trades",
            "min_qqq_cagr_delta",
            "series_data_path",
            "repeat_generations",
            "interval_seconds",
            "parameter_domains",
            "dashboard_port",
            "docker_image",
            "env_file",
        }


def test_phase0_dashboard_http_surface_is_frozen() -> None:
    app = create_app()
    routes = {
        (method, route.path)
        for route in app.routes
        if getattr(route, "path", "").startswith(("/",))
        and route.path != "/openapi.json"
        and not route.path.startswith("/static")
        for method in (getattr(route, "methods", set()) or set())
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }
    assert routes == EXPECTED_DASHBOARD_ROUTES


def test_phase0_strategy_ir_shape_is_frozen() -> None:
    actual = {
        name: (field.alias, field.is_required())
        for name, field in StrategyIR.model_fields.items()
    }
    assert actual == EXPECTED_STRATEGY_FIELDS


def test_phase0_canonical_generation_stage_names_are_frozen() -> None:
    assert CANONICAL_STAGES == EXPECTED_CANONICAL_STAGES


def test_phase0_primary_application_entrypoints_remain_available(tmp_path: Path) -> None:
    assert callable(run_local_evaluation)
    assert callable(run_autoresearch)
    assert callable(create_mcp_server)

    service = DashboardService(tmp_path)
    assert callable(service.snapshot)
    server = create_mcp_server(state_dir=tmp_path / "state", project_root=tmp_path)
    assert callable(server.handle)
