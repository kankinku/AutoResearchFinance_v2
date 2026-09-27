from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from application.services import ApplicationServices, create_application_services
from integrations.codex_mcp_protocol import error, serve_lines, success, text_content
from orchestration.evaluation_runner import parse_parameter_domains
from research.llm.codex_exec import write_provider_status
from research.llm.codex_schema import research_intent_schema
from research.policy import default_evaluation_thresholds
from runtime.system_controller import SystemLaunchConfig

_EVALUATION_DEFAULTS = default_evaluation_thresholds()

_SUBMIT_INTENT_REPLACEMENTS = (
    "start_system",
    "run_evaluation",
    "validate_strategy",
    "get_system_status",
)

_TARGET_PUBLIC_TOOL_NAMES = frozenset(
    {
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
)

_LEGACY_INTERNAL_REPLACEMENTS: dict[str, tuple[str, ...]] = {
    "set_research_mode": ("get_workspace_status",),
    "validate_research_cache": (),
    "plan_generation": ("start_system", "run_evaluation"),
    "get_research_context": (
        "list_features",
        "get_research_evidence",
        "get_dashboard_status",
        "get_system_status",
    ),
}


class CodexMCPServer:
    def __init__(self, *, state_dir: Path, project_root: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.project_root = project_root.resolve()
        self.services: ApplicationServices = create_application_services(
            state_dir=self.state_dir,
            project_root=self.project_root,
        )
        self.dashboard = self.services.dashboard
        self.system = self.services.system.controller

    def handle(self, request: object) -> dict[str, Any] | None:
        if not isinstance(request, Mapping):
            return error(None, -32600, "invalid request")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return error(request_id, -32600, "method is required")
        if method in {"initialize", "ping", "tools/list"}:
            write_provider_status(
                self.state_dir / "llm" / "status.json",
                "codex_desktop",
                "ONLINE",
                "MCP_CONNECTED",
            )
        if "id" not in request and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return success(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "quant-autoresearch", "version": "0.1.0"},
                },
            )
        if method == "ping":
            return success(request_id, {})
        if method == "tools/list":
            return success(request_id, {"tools": _tools()})
        if method == "tools/call":
            return self._call(request_id, request.get("params"))
        if method == "notifications/initialized":
            return None
        return error(request_id, -32601, "method not found")

    def _call(self, request_id: object, params: object) -> dict[str, Any]:
        if not isinstance(params, Mapping) or not isinstance(params.get("name"), str):
            return error(request_id, -32602, "tool name is required")
        name = str(params["name"])
        arguments = params.get("arguments", {})
        if not isinstance(arguments, Mapping):
            return _tool_error(request_id, "tool arguments must be an object")
        try:
            payload = self._dispatch(name, dict(arguments))
            payload = _with_legacy_compatibility(name, payload)
        except (OSError, PermissionError, TypeError, ValueError):
            return _tool_error(request_id, "tool request failed")
        return success(request_id, {"content": text_content(payload), "isError": False})

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> object:
        if name == "initialize_research_state":
            if arguments:
                raise ValueError("initialization takes no arguments")
            return self.services.workspace.initialize()
        if name == "get_workspace_status":
            if arguments:
                raise ValueError("workspace status takes no arguments")
            return self.services.workspace.status()
        if name == "set_research_mode":
            if set(arguments) != {"mode"}:
                raise ValueError("set_research_mode requires only mode")
            mode = arguments.get("mode")
            if not isinstance(mode, str):
                raise ValueError("mode must be a string")
            return self.services.workspace.set_mode(mode)
        if name == "validate_research_cache":
            if set(arguments) - {"manifest_dir"}:
                raise ValueError("unexpected cache validation arguments")
            manifest_dir = arguments.get("manifest_dir", "manifests")
            if not isinstance(manifest_dir, str) or not manifest_dir.strip():
                raise ValueError("manifest_dir must be a string")
            return self.services.workspace.validate_cache(manifest_dir=manifest_dir)
        if name == "validate_strategy":
            source_path = arguments.get("source_path")
            if not isinstance(source_path, str) or not source_path.strip():
                raise ValueError("source_path is required")
            if set(arguments) - {"source_path"}:
                raise ValueError("unexpected strategy validation arguments")
            return self.services.strategy.validate(source_path)
        if name == "import_strategies":
            return self._import_strategies(arguments)
        if name == "list_strategies":
            strategies_dir = arguments.get("strategies_dir", "strategies")
            if not isinstance(strategies_dir, str) or not strategies_dir.strip():
                raise ValueError("strategies_dir must be a string")
            if set(arguments) - {"strategies_dir"}:
                raise ValueError("unexpected strategy list arguments")
            return self.services.strategy.list_strategies(strategies_dir=strategies_dir)
        if name == "plan_generation":
            return self._plan_generation(arguments)
        if name == "get_research_context":
            return self._research_context()
        if name == "list_features":
            return {"features": self.services.catalog.research_features()}
        if name == "get_research_evidence":
            run_id = arguments.get("research_run_id")
            if run_id is not None and not isinstance(run_id, str):
                raise ValueError("research_run_id must be a string")
            if set(arguments) - {"research_run_id"}:
                raise ValueError("unexpected evidence arguments")
            return self.services.research.evidence(run_id)
        if name == "get_dashboard_status":
            return self.services.dashboard.snapshot().model_dump(mode="json")
        if name == "submit_research_intent":
            return self._submit_intent(arguments)
        if name == "run_evaluation":
            return self._run_evaluation(arguments)
        if name == "check_system":
            return self.services.system.preflight(_system_config(arguments))
        if name == "start_system":
            return self.services.system.start(_system_config(arguments))
        if name == "get_system_status":
            return self.services.system.status()
        if name == "stop_system":
            return self.services.system.stop()
        raise ValueError("unknown tool")

    def _import_strategies(self, arguments: dict[str, Any]) -> dict[str, object]:
        allowed = {
            "source_path",
            "repository_url",
            "ref",
            "strategies_dir",
            "dry_run",
            "kis_presets",
        }
        if set(arguments) - allowed:
            raise ValueError("unexpected strategy import arguments")
        source_path = arguments.get("source_path")
        repository_url = arguments.get("repository_url")
        ref = arguments.get("ref", "main")
        strategies_dir = arguments.get("strategies_dir", "strategies")
        dry_run = arguments.get("dry_run", True)
        kis_presets = arguments.get("kis_presets", False)
        if source_path is not None and not isinstance(source_path, str):
            raise ValueError("source_path must be a string")
        if repository_url is not None and not isinstance(repository_url, str):
            raise ValueError("repository_url must be a string")
        if not isinstance(ref, str) or not isinstance(strategies_dir, str):
            raise ValueError("strategy import string options are invalid")
        if not isinstance(dry_run, bool) or not isinstance(kis_presets, bool):
            raise ValueError("strategy import boolean options are invalid")
        return self.services.strategy.import_strategies(
            source_path=source_path,
            repository_url=repository_url,
            ref=ref,
            strategies_dir=strategies_dir,
            dry_run=dry_run,
            kis_presets=kis_presets,
        )

    def _plan_generation(self, arguments: dict[str, Any]) -> dict[str, object]:
        allowed = {"parent_ids", "method", "count", "seed"}
        if set(arguments) - allowed:
            raise ValueError("unexpected generation plan arguments")
        parent_ids = arguments.get("parent_ids")
        if not isinstance(parent_ids, list) or not parent_ids:
            raise ValueError("parent_ids must be a non-empty array")
        if any(not isinstance(item, str) or not item.strip() for item in parent_ids):
            raise ValueError("parent_ids must contain non-empty strings")
        method = arguments.get("method")
        if not isinstance(method, str):
            raise ValueError("method is required")
        return self.services.planning.plan_generation(
            parent_ids=tuple(parent_ids),
            method=method,
            count=_positive_int(arguments.get("count"), "count"),
            seed=_nonnegative_int(arguments.get("seed"), "seed"),
        )

    def _research_context(self) -> dict[str, object]:
        return self.services.research.context()

    def _feature_catalog(self) -> list[dict[str, object]]:
        return self.services.catalog.research_features()

    def _submit_intent(self, arguments: dict[str, Any]) -> dict[str, object]:
        return self.services.research.validate_and_record_intent(arguments)

    def _run_evaluation(self, arguments: dict[str, Any]) -> dict[str, object]:
        method = str(arguments.get("method", "grid"))
        count = _positive_int(arguments.get("count", 1), "count")
        seed = _nonnegative_int(arguments.get("seed", 0), "seed")
        min_trades = _nonnegative_int(arguments.get("min_trades", 10), "min_trades")
        min_annual_trades = _nonnegative_int(
            arguments.get("min_annual_trades", _EVALUATION_DEFAULTS.min_annual_trades),
            "min_annual_trades",
        )
        min_qqq_cagr = _optional_float(
            arguments.get("min_qqq_cagr_delta", _EVALUATION_DEFAULTS.min_qqq_cagr_delta),
            "min_qqq_cagr_delta",
        )
        parameter_domains = parse_parameter_domains(arguments.get("parameter_domains"))
        return self.services.evaluation.run(
            source_path=arguments.get("source_path"),
            data_path=arguments.get("data_path"),
            method=method,
            count=count,
            seed=seed,
            min_trades=min_trades,
            min_annual_trades=min_annual_trades,
            parameter_domains=parameter_domains,
            series_data_path=arguments.get("series_data_path"),
            min_qqq_cagr_delta=min_qqq_cagr,
        )


def create_mcp_server(*, state_dir: Path, project_root: Path) -> CodexMCPServer:
    return CodexMCPServer(state_dir=state_dir, project_root=project_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-autoresearch-codex-mcp")
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    serve_lines(
        create_mcp_server(state_dir=args.state_dir, project_root=args.project_root),
        sys.stdin,
        sys.stdout,
    )
    return 0


def _all_tools() -> list[dict[str, object]]:
    """Return public and compatibility-only tool definitions."""

    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    return [
        {
            "name": "initialize_research_state",
            "description": (
                "Initialize missing paper-research state files without enabling orders. "
                "Existing state is always preserved."
            ),
            "inputSchema": empty,
        },
        {
            "name": "get_workspace_status",
            "description": (
                "Read sanitized research workspace state, mode, audit count, and manifest count."
            ),
            "inputSchema": empty,
        },
        {
            "name": "set_research_mode",
            "description": (
                "Select paper or live mode state while keeping orders_enabled=false. "
                "This does not grant trading permission."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "mode": {"enum": ["paper", "live"], "type": "string"},
                },
                "required": ["mode"],
                "additionalProperties": False,
            },
        },
        {
            "name": "validate_research_cache",
            "description": (
                "Validate experiment manifest files and report the valid manifest count."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "manifest_dir": {"type": "string", "default": "manifests"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "validate_strategy",
            "description": (
                "Statically validate and normalize one project strategy source without "
                "executing it."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"source_path": {"type": "string"}},
                "required": ["source_path"],
                "additionalProperties": False,
            },
        },
        {
            "name": "import_strategies",
            "description": (
                "Statically scan a project source or HTTPS GitHub repository. "
                "dry_run defaults to true; imported source is never executed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_path": {"type": "string"},
                    "repository_url": {"type": "string"},
                    "ref": {"type": "string", "default": "main"},
                    "strategies_dir": {"type": "string", "default": "strategies"},
                    "dry_run": {"type": "boolean", "default": True},
                    "kis_presets": {"type": "boolean", "default": False},
                },
                "oneOf": [
                    {"required": ["source_path"]},
                    {"required": ["repository_url"]},
                ],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_strategies",
            "description": "List sanitized records from the local imported strategy catalog.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "strategies_dir": {"type": "string", "default": "strategies"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "plan_generation",
            "description": (
                "Create a deterministic local experiment plan without executing research."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parent_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "method": {
                        "enum": ["grid", "random", "bayesian"],
                        "type": "string",
                    },
                    "count": {"minimum": 1, "type": "integer"},
                    "seed": {"minimum": 0, "type": "integer"},
                },
                "required": ["parent_ids", "method", "count", "seed"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_research_context",
            "description": "Read sanitized research context.",
            "inputSchema": empty,
        },
        {
            "name": "list_features",
            "description": "List selectable feature candidates.",
            "inputSchema": empty,
        },
        {
            "name": "get_research_evidence",
            "description": "Read attributable research evidence; sealed OOS remains NOT_MEASURED.",
            "inputSchema": {
                "type": "object",
                "properties": {"research_run_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "get_dashboard_status",
            "description": "Read local operations status.",
            "inputSchema": empty,
        },
        {
            "name": "submit_research_intent",
            "description": (
                "[DEPRECATED] Validate and record a ResearchIntent only; this does not "
                "execute research. Use start_system for managed research, run_evaluation "
                "for one-shot evaluation, validate_strategy for static validation, and "
                "get_system_status for progress."
            ),
            "inputSchema": research_intent_schema(),
        },
        {
            "name": "run_evaluation",
            "description": "Run a local deterministic evaluation over approved project inputs.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_path": {"type": "string"},
                    "data_path": {"type": "string"},
                    "method": {"enum": ["grid", "random", "bayesian"], "type": "string"},
                    "count": {"minimum": 1, "type": "integer"},
                    "seed": {"minimum": 0, "type": "integer"},
                    "min_trades": {"minimum": 0, "type": "integer"},
                    "min_annual_trades": {
                        "minimum": 0,
                        "type": "integer",
                        "default": _EVALUATION_DEFAULTS.min_annual_trades,
                    },
                    "parameter_domains": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "values": {"type": "array"},
                            },
                            "required": ["name", "values"],
                            "additionalProperties": False,
                        },
                    },
                    "series_data_path": {"type": "string"},
                    "min_qqq_cagr_delta": {
                        "type": "number",
                        "default": _EVALUATION_DEFAULTS.min_qqq_cagr_delta,
                    },
                },
                "required": ["source_path", "data_path"],
                "additionalProperties": False,
            },
        },
        {
            "name": "check_system",
            "description": (
                "Check all prerequisites before starting the local paper research system."
            ),
            "inputSchema": _system_schema(),
        },
        {
            "name": "start_system",
            "description": (
                "Start the dashboard and canonical research loop; evaluations use the "
                "configured local scheduler or isolated Docker job backend."
            ),
            "inputSchema": _system_schema(),
        },
        {
            "name": "get_system_status",
            "description": "Read managed system and worker status.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "stop_system",
            "description": "Stop the managed local research and backtest system.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


def _tools() -> list[dict[str, object]]:
    """Return the default public MCP surface."""

    return [
        tool
        for tool in _all_tools()
        if isinstance(tool.get("name"), str)
        and tool["name"] in _TARGET_PUBLIC_TOOL_NAMES
    ]


def _with_legacy_compatibility(name: str, payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    if name == "submit_research_intent":
        return {
            **payload,
            "_compatibility": {
                "status": "DEPRECATED",
                "replacement_tools": list(_SUBMIT_INTENT_REPLACEMENTS),
                "note": (
                    "This tool only validates and records an intent; it does not execute "
                    "research. Use start_system for managed research or run_evaluation "
                    "for one-shot evaluation."
                ),
            },
        }
    replacements = _LEGACY_INTERNAL_REPLACEMENTS.get(name)
    if replacements is None:
        return payload
    note = (
        "This compatibility-only tool is no longer advertised in tools/list. "
        "Use the listed public replacement tools or the documented host/CLI path."
    )
    return {
        **payload,
        "_compatibility": {
            "status": "LEGACY_INTERNAL_TOOL",
            "replacement_tools": list(replacements),
            "note": note,
        },
    }


def _system_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "source_path": {"type": "string"},
            "data_path": {"type": "string"},
            "method": {"enum": ["grid", "random", "bayesian"], "type": "string"},
            "count": {"minimum": 1, "type": "integer"},
            "seed": {"minimum": 0, "type": "integer"},
            "min_trades": {"minimum": 0, "type": "integer"},
            "min_annual_trades": {
                "minimum": 0,
                "type": "integer",
                "default": _EVALUATION_DEFAULTS.min_annual_trades,
            },
            "min_qqq_cagr_delta": {
                "type": "number",
                "default": _EVALUATION_DEFAULTS.min_qqq_cagr_delta,
            },
            "series_data_path": {"type": "string"},
            "repeat_generations": {"minimum": 1, "type": "integer", "default": 1},
            "interval_seconds": {"minimum": 0, "type": "number", "default": 0},
            "parameter_domains": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "values": {"type": "array"},
                    },
                    "required": ["name", "values"],
                    "additionalProperties": False,
                },
            },
            "dashboard_port": {"minimum": 1, "maximum": 65535, "type": "integer"},
            "docker_image": {"type": "string"},
            "env_file": {"type": "string"},
        },
        "required": ["source_path", "data_path"],
        "additionalProperties": False,
    }


def _system_config(arguments: dict[str, Any]) -> SystemLaunchConfig:
    source_path = arguments.get("source_path")
    data_path = arguments.get("data_path")
    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError("source_path is required")
    if not isinstance(data_path, str) or not data_path.strip():
        raise ValueError("data_path is required")
    method = arguments.get("method", "random")
    docker_image = arguments.get("docker_image", "quant-autoresearch-worker:local")
    env_file = arguments.get("env_file", ".env")
    if not all(
        isinstance(value, str) and value.strip() for value in (method, docker_image, env_file)
    ):
        raise ValueError("system string options are invalid")
    return SystemLaunchConfig(
        source_path=source_path,
        data_path=data_path,
        method=method,
        count=_positive_int(arguments.get("count", 8), "count"),
        seed=_nonnegative_int(arguments.get("seed", 0), "seed"),
        min_trades=_nonnegative_int(arguments.get("min_trades", 10), "min_trades"),
        min_annual_trades=_nonnegative_int(
            arguments.get("min_annual_trades", _EVALUATION_DEFAULTS.min_annual_trades),
            "min_annual_trades",
        ),
        min_qqq_cagr_delta=_optional_float(
            arguments.get("min_qqq_cagr_delta", _EVALUATION_DEFAULTS.min_qqq_cagr_delta),
            "min_qqq_cagr_delta",
        ),
        series_data_path=(
            arguments.get("series_data_path")
            if isinstance(arguments.get("series_data_path"), str)
            else None
        ),
        repeat_generations=_positive_int(
            arguments.get("repeat_generations", 1), "repeat_generations"
        ),
        interval_seconds=_nonnegative_float(
            arguments.get("interval_seconds", 0), "interval_seconds"
        ),
        parameter_domains=parse_parameter_domains(arguments.get("parameter_domains")),
        dashboard_port=_positive_int(arguments.get("dashboard_port", 8080), "dashboard_port"),
        docker_image=docker_image,
        env_file=env_file,
    )


def _tool_error(request_id: object, message: str) -> dict[str, Any]:
    return success(
        request_id,
        {"content": text_content({"status": "ERROR", "message": message}), "isError": True},
    )


def _positive_int(value: object, name: str) -> int:
    result = _integer(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _nonnegative_int(value: object, name: str) -> int:
    result = _integer(value, name)
    if result < 0:
        raise ValueError(f"{name} cannot be negative")
    return result


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _optional_float(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


def _nonnegative_float(value: object, name: str) -> float:
    result = _optional_float(value, name)
    assert result is not None
    if result < 0:
        raise ValueError(f"{name} cannot be negative")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
