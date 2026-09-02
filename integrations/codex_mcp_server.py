from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.features.registry import default_feature_registry
from dashboard.service import DashboardService
from integrations.codex_mcp_protocol import error, serve_lines, success, text_content
from orchestration.evaluation_runner import run_local_evaluation
from research.llm.codex_exec import record_intent, sanitize_context, write_provider_status
from research.llm.codex_schema import research_intent_schema
from research.llm.director import ResearchIntent
from runtime.system_controller import SystemController, SystemLaunchConfig


class CodexMCPServer:
    def __init__(self, *, state_dir: Path, project_root: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.project_root = project_root.resolve()
        self.dashboard = DashboardService(self.state_dir)
        self.system = SystemController(state_dir=self.state_dir, project_root=self.project_root)

    def handle(self, request: object) -> dict[str, Any] | None:
        if not isinstance(request, Mapping):
            return error(None, -32600, "invalid request")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return error(request_id, -32600, "method is required")
        if method in {"initialize", "ping", "tools/list", "tools/call"}:
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
        except (OSError, PermissionError, TypeError, ValueError):
            return _tool_error(request_id, "tool request failed")
        return success(request_id, {"content": text_content(payload), "isError": False})

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> object:
        if name == "get_research_context":
            return self._research_context()
        if name == "list_features":
            return {
                "features": [
                    {
                        "name": spec.name,
                        "family": spec.family,
                        "inputs": list(spec.inputs),
                        "calculator": spec.calculator,
                        "lookback": spec.lookback,
                        "timeframe": spec.timeframe,
                    }
                    for spec in default_feature_registry().all()
                ]
            }
        if name == "get_dashboard_status":
            return self.dashboard.snapshot().model_dump(mode="json")
        if name == "submit_research_intent":
            return self._submit_intent(arguments)
        if name == "run_evaluation":
            return self._run_evaluation(arguments)
        if name == "check_system":
            return self.system.preflight(_system_config(arguments)).as_payload()
        if name == "start_system":
            return self.system.start(_system_config(arguments))
        if name == "get_system_status":
            return self.system.status()
        if name == "stop_system":
            return self.system.stop()
        raise ValueError("unknown tool")

    def _research_context(self) -> dict[str, object]:
        snapshot = self.dashboard.snapshot()
        observations = [
            {
                "run_id": item.run_id,
                "strategy_hash": item.strategy_hash,
                "generation": item.generation,
                "score": item.score,
                "total_return": item.total_return,
                "nasdaq_excess_return": item.nasdaq_excess_return,
                "max_drawdown": item.max_drawdown,
                "risk_compliant": item.risk_compliant,
                "status": item.status,
            }
            for item in snapshot.tests[:20]
        ]
        payload = sanitize_context(
            {
                "generation": snapshot.strategy.generation or 0,
                "champion": snapshot.strategy.model_dump(mode="json"),
                "frontier": [],
                "observations": observations,
                "feature_catalog": self._feature_catalog(),
            }
        )
        if not isinstance(payload, dict):
            raise ValueError("research context must be an object")
        return payload

    def _feature_catalog(self) -> list[dict[str, object]]:
        return [
            {
                "name": spec.name,
                "family": spec.family,
                "inputs": list(spec.inputs),
                "calculator": spec.calculator,
                "lookback": spec.lookback,
                "timeframe": spec.timeframe,
            }
            for spec in default_feature_registry().all()
        ]

    def _submit_intent(self, arguments: dict[str, Any]) -> dict[str, object]:
        intent = ResearchIntent.model_validate(arguments)
        payload = sanitize_context(intent.model_dump(mode="json", exclude_none=True))
        record_intent(self.state_dir / "llm" / "intents.jsonl", intent)
        return {"status": "VALIDATED", "intent": payload}

    def _run_evaluation(self, arguments: dict[str, Any]) -> dict[str, object]:
        method = str(arguments.get("method", "grid"))
        count = _positive_int(arguments.get("count", 1), "count")
        seed = _nonnegative_int(arguments.get("seed", 0), "seed")
        min_trades = _nonnegative_int(arguments.get("min_trades", 10), "min_trades")
        return run_local_evaluation(
            project_root=self.project_root,
            state_dir=self.state_dir,
            source_path=arguments.get("source_path"),
            data_path=arguments.get("data_path"),
            method=method,
            count=count,
            seed=seed,
            min_trades=min_trades,
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


def _tools() -> list[dict[str, object]]:
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    return [
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
            "name": "get_dashboard_status",
            "description": "Read local operations status.",
            "inputSchema": empty,
        },
        {
            "name": "submit_research_intent",
            "description": "Validate and record a ResearchIntent.",
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
                "Start dashboard, research detection, and isolated Docker backtesting in parallel."
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


if __name__ == "__main__":
    raise SystemExit(main())
