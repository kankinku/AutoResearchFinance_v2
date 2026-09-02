from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from orchestration.evaluation_runner import (
    ALLOWED_STRATEGY_SUFFIXES,
    build_research_context,
    parse_parameter_domains,
    resolve_project_input,
)
from research.llm.codex_exec import CodexExecProvider, record_intent
from research.llm.director import ResearchDirector, ResearchIntent
from runtime.research_loop import ResearchLoopConfig, run_repeated_evaluation


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    state_dir = Path(args.state_dir)
    try:
        _write_status(state_dir, args.role, "RUNNING")
        if args.role == "research":
            result = _run_research(args, state_dir)
        else:
            result = run_repeated_evaluation(
                ResearchLoopConfig(
                    project_root=Path(args.project_root),
                    state_dir=state_dir,
                    source_path=args.source_path,
                    data_path=args.data_path,
                    method=args.method,
                    count=args.count,
                    seed=args.seed,
                    min_trades=args.min_trades,
                    min_annual_trades=args.min_annual_trades,
                    min_qqq_cagr_delta=args.min_qqq_cagr_delta,
                    series_data_path=args.series_data_path,
                    generations=args.repeat_generations,
                    interval_seconds=args.interval_seconds,
                    parameter_domains=parse_parameter_domains(
                        [json.loads(document) for document in args.domain]
                    ),
                )
            )
        _write_status(state_dir, args.role, "SUCCEEDED", result=result)
        return 0
    except (OSError, PermissionError, TypeError, ValueError) as exc:
        _write_status(state_dir, args.role, "FAILED", error=type(exc).__name__)
        return 2


def _run_research(args: argparse.Namespace, state_dir: Path) -> dict[str, object]:
    project_root = Path(args.project_root).resolve()
    source = resolve_project_input(project_root, args.source_path, ALLOWED_STRATEGY_SUFFIXES)
    context = build_research_context(state_dir, source_path=source)
    provider = CodexExecProvider.from_env(
        Path(args.env_file),
        workdir=project_root,
        status_path=state_dir / "llm" / "status.json",
    )
    intent = ResearchIntent.model_validate(ResearchDirector(provider).propose(context))
    record_intent(state_dir / "llm" / "intents.jsonl", intent)
    return {"status": "INTENT_RECORDED", "mode": intent.mode, "parent_ids": list(intent.parent_ids)}


def _write_status(
    state_dir: Path,
    role: str,
    status: str,
    *,
    error: str | None = None,
    result: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {"role": role, "status": status}
    if error is not None:
        payload["error"] = error
    if result is not None:
        payload["result"] = result
    target = state_dir / "system" / f"{role}_worker.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, target)
    except OSError:
        return


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant-autoresearch-system-worker")
    parser.add_argument("--role", choices=("research", "backtest"), required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--source-path", default="")
    parser.add_argument("--data-path", default="")
    parser.add_argument("--method", choices=("grid", "random", "bayesian"), default="random")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--min-annual-trades", type=int, default=30)
    parser.add_argument("--min-qqq-cagr-delta", type=float)
    parser.add_argument("--series-data-path", default=None)
    parser.add_argument("--repeat-generations", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--domain", action="append", default=[])
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
