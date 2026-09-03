from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from dashboard.state import DashboardStateReader
from orchestration.evaluation_runner import parse_parameter_domains
from research.llm.codex_exec import CodexExecProvider, _read_settings
from research.llm.director import ResearchDirector
from research.policy import default_evaluation_thresholds
from runtime.research_loop import ResearchLoopConfig, run_autoresearch
from runtime.terminal import CodexChatProvider, terminal_help

_EVALUATION_DEFAULTS = default_evaluation_thresholds()


@dataclass(frozen=True)
class MimirCommand:
    name: str
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchPaths:
    source: str
    data: str
    series_data: str | None = None


@dataclass(frozen=True)
class MimirResearchOptions:
    generations: int
    source: str | None
    data: str | None
    series_data: str | None
    method: str
    count: int
    seed: int
    min_trades: int
    min_annual_trades: int
    min_qqq_cagr: float | None
    domains: tuple[str, ...]
    intent_repair_attempts: int
    state_dir: Path
    env_file: Path
    project_root: Path


def parse_mimir_command(argv: Sequence[str]) -> MimirCommand:
    if not argv:
        raise ValueError("Mimir command is required")
    name = argv[0].lstrip("/").lower()
    if name not in {"research", "status", "help", "stop", "chat"}:
        raise ValueError(f"unknown Mimir command: {argv[0]}")
    arguments = tuple(argv[1:])
    if name == "research":
        if not arguments or not arguments[0].isdigit() or int(arguments[0]) <= 0:
            raise ValueError("research requires a positive integer generation count")
    elif name == "chat" and not arguments:
        raise ValueError("chat requires a prompt")
    elif name in {"status", "help", "stop"} and arguments:
        raise ValueError(f"{name} does not accept arguments")
    return MimirCommand(name, arguments)


def resolve_research_paths(
    *,
    source: str | None,
    data: str | None,
    series_data: str | None,
    env_values: Mapping[str, str],
    state_dir: Path,
) -> ResearchPaths:
    state_values = _read_last_research_config(state_dir)
    resolved_source = _first_value(
        source, env_values.get("MIMIR_SOURCE"), state_values.get("source_path")
    )
    resolved_data = _first_value(
        data, env_values.get("MIMIR_DATA"), state_values.get("data_path")
    )
    resolved_series = _first_value(
        series_data,
        env_values.get("MIMIR_SERIES_DATA"),
        state_values.get("series_data_path"),
    )
    if resolved_source is None or resolved_data is None:
        raise ValueError(
            "research paths are missing; set --source/--data or "
            "MIMIR_SOURCE/MIMIR_DATA in .env"
        )
    return ResearchPaths(resolved_source, resolved_data, resolved_series)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        command = parse_mimir_command(tuple(argv) if argv is not None else _command_argv())
        if command.name == "help":
            print(terminal_help())
            print(
                "Mimir /research <generations> [--source PATH --data PATH "
                "--intent-repairs N]"
            )
            print("Mimir /status | Mimir /chat \"질문\" | Mimir /stop")
            return 0
        if command.name == "status":
            state_dir = _common_state_dir(command.arguments)
            snapshot = DashboardStateReader(state_dir).read().model_dump(mode="json")
            print(json.dumps(snapshot, ensure_ascii=False))
            return 0
        if command.name == "stop":
            print(json.dumps({"status": "STOP_REQUESTED", "orders_enabled": False}))
            return 0
        if command.name == "chat":
            options = _parse_common_options(())
            chat_provider = CodexChatProvider.from_env(
                options.env_file, workdir=options.project_root
            )
            print(chat_provider.ask(" ".join(command.arguments)))
            return 0
        options = _parse_research_options(command.arguments)
        settings = _read_settings(options.env_file)
        paths = resolve_research_paths(
            source=options.source,
            data=options.data,
            series_data=options.series_data,
            env_values=settings,
            state_dir=options.state_dir,
        )
        director = ResearchDirector(_codex_provider(options))
        result = run_autoresearch(
            ResearchLoopConfig(
                project_root=options.project_root,
                state_dir=options.state_dir,
                source_path=paths.source,
                data_path=paths.data,
                series_data_path=paths.series_data,
                method=options.method,
                count=options.count,
                seed=options.seed,
                min_trades=options.min_trades,
                min_annual_trades=options.min_annual_trades,
                min_qqq_cagr_delta=options.min_qqq_cagr,
                parameter_domains=parse_parameter_domains(
                    [json.loads(document) for document in options.domains]
                ),
                generations=options.generations,
                intent_repair_attempts=options.intent_repair_attempts,
            ),
            director,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "reason": str(exc)}, ensure_ascii=False))
        return 2


def _command_argv() -> tuple[str, ...]:
    import sys

    return tuple(sys.argv[1:])


def _parse_common_options(arguments: Sequence[str]) -> MimirResearchOptions:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parsed = parser.parse_args(list(arguments))
    return MimirResearchOptions(
        generations=1,
        source=None,
        data=None,
        series_data=None,
        method="random",
        count=8,
        seed=0,
        min_trades=10,
        min_annual_trades=_EVALUATION_DEFAULTS.min_annual_trades,
        min_qqq_cagr=_EVALUATION_DEFAULTS.min_qqq_cagr_delta,
        domains=(),
        intent_repair_attempts=3,
        state_dir=parsed.state_dir,
        env_file=parsed.env_file,
        project_root=parsed.project_root,
    )


def _parse_research_options(arguments: Sequence[str]) -> MimirResearchOptions:
    parser = argparse.ArgumentParser(prog="Mimir /research")
    parser.add_argument("generations", type=int)
    parser.add_argument("--source")
    parser.add_argument("--data")
    parser.add_argument("--series-data")
    parser.add_argument("--method", choices=("grid", "random", "bayesian"), default="random")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument(
        "--min-annual-trades", type=int, default=_EVALUATION_DEFAULTS.min_annual_trades
    )
    parser.add_argument(
        "--min-qqq-cagr",
        type=float,
        default=_EVALUATION_DEFAULTS.min_qqq_cagr_delta,
        help=(
            "QQQ 대비 최소 연복리 초과수익률 "
            f"(기본값: {_EVALUATION_DEFAULTS.min_qqq_cagr_delta:g})"
        ),
    )
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--intent-repairs", type=int, default=3)
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parsed = parser.parse_args(list(arguments))
    if parsed.generations <= 0:
        raise ValueError("research requires a positive integer generation count")
    if parsed.intent_repairs < 0:
        raise ValueError("--intent-repairs cannot be negative")
    return MimirResearchOptions(
        generations=parsed.generations,
        source=parsed.source,
        data=parsed.data,
        series_data=parsed.series_data,
        method=parsed.method,
        count=parsed.count,
        seed=parsed.seed,
        min_trades=parsed.min_trades,
        min_annual_trades=parsed.min_annual_trades,
        min_qqq_cagr=parsed.min_qqq_cagr,
        domains=tuple(parsed.domain),
        intent_repair_attempts=parsed.intent_repairs,
        state_dir=parsed.state_dir,
        env_file=parsed.env_file,
        project_root=parsed.project_root,
    )


def _codex_provider(options: MimirResearchOptions) -> CodexExecProvider:
    return CodexExecProvider.from_env(
        options.env_file,
        workdir=options.project_root,
        status_path=options.state_dir / "llm" / "status.json",
    )


def _common_state_dir(arguments: Sequence[str]) -> Path:
    options = _parse_common_options(arguments)
    return options.state_dir


def _read_last_research_config(state_dir: Path) -> dict[str, str]:
    path = state_dir / "system" / "research_loop.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    config = payload.get("config") if isinstance(payload, Mapping) else None
    if not isinstance(config, Mapping):
        return {}
    return {
        key: str(value)
        for key, value in config.items()
        if key in {"source_path", "data_path", "series_data_path"} and value
    }


def _first_value(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


if __name__ == "__main__":
    raise SystemExit(main())
