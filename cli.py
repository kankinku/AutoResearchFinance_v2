from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from dashboard.run import run_dashboard
from dashboard.service import DashboardService
from dashboard.state import DashboardStateReader
from experiments.planner import plan_experiment
from integrations.kis.client import KISAPIError
from integrations.kis.config import KISConfigError, PaperKISConfig
from integrations.kis.paper_orders import KISPaperOrderClient, PaperOrderError
from memory.state_files import StateFileStore
from orchestration.evaluation_runner import parse_parameter_domains, run_local_evaluation
from research.llm.codex_exec import CodexExecProvider, record_intent, sanitize_context
from research.llm.director import ResearchDirector
from runtime.research_loop import ResearchLoopConfig, run_autoresearch, run_repeated_evaluation
from runtime.terminal import (
    CodexChatProvider,
    parse_terminal_command,
    terminal_help,
    validate_direct_edit_gate,
)
from strategy_import.pipeline import import_local_source
from strategy_import.sources import CloneManager, parse_github_source
from strategy_ir.normalizer import ImportStatus, normalize_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant-autoresearch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "status"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    for command in ("mode", "set-mode"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    subparsers.add_parser("list-features")
    research_parser = subparsers.add_parser(
        "research-intent", help="Ask the local Codex CLI for one validated research intent"
    )
    research_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    research_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    research_parser.add_argument("--project-root", type=Path, default=Path("."))
    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    dashboard_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    dashboard_parser.add_argument("--host", default="127.0.0.1")
    dashboard_parser.add_argument("--port", type=int, default=8080)
    for command in ("dashboard-status", "dashboard-refresh"):
        dashboard_command = subparsers.add_parser(command)
        dashboard_command.add_argument("--state-dir", type=Path, default=Path("state"))
        dashboard_command.add_argument("--env-file", type=Path, default=Path(".env"))
    paper_order_parser = subparsers.add_parser(
        "paper-order-smoke", help="Submit one paper buy, verify fill, then submit its sell"
    )
    paper_order_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    paper_order_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    paper_order_parser.add_argument("--symbol", default="QQQ")
    paper_order_parser.add_argument("--quantity", type=int, default=1)
    paper_order_parser.add_argument(
        "--exchange", choices=("NASD", "NYSE", "AMEX"), default="NASD"
    )
    paper_order_parser.add_argument("--timeout-seconds", type=float, default=30.0)
    paper_order_parser.add_argument("--poll-seconds", type=float, default=1.0)
    paper_order_parser.add_argument("--confirm-paper-order", action="store_true")
    subparsers.choices["set-mode"].add_argument(
        "--mode", choices=("paper", "live"), required=True
    )
    for command in ("import-strategy", "validate-strategy"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--source", type=Path, required=True)
    import_parser = subparsers.add_parser(
        "import-strategies", help="Clone or scan strategy sources without executing external code"
    )
    import_group = import_parser.add_mutually_exclusive_group(required=True)
    import_group.add_argument("--source", type=Path)
    import_group.add_argument("--repo")
    import_parser.add_argument("--ref", default="main")
    import_parser.add_argument("--strategies-dir", type=Path, default=Path("strategies"))
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.add_argument("--kis-presets", action="store_true")
    plan_parser = subparsers.add_parser("plan-generation")
    plan_parser.add_argument("--parent", action="append", required=True, dest="parents")
    plan_parser.add_argument("--method", choices=("grid", "random", "bayesian"), required=True)
    plan_parser.add_argument("--count", type=int, required=True)
    plan_parser.add_argument("--seed", type=int, required=True)
    run_parser = subparsers.add_parser("run-generation")
    run_parser.add_argument("--source", type=Path, required=True)
    run_parser.add_argument("--data", type=Path, required=True)
    run_parser.add_argument("--method", choices=("grid", "random", "bayesian"), default="grid")
    run_parser.add_argument("--count", type=int, default=1)
    run_parser.add_argument("--seed", type=int, default=0)
    run_parser.add_argument("--min-trades", type=int, default=10)
    run_parser.add_argument("--min-annual-trades", type=int, default=30)
    run_parser.add_argument(
        "--min-qqq-cagr",
        type=float,
        help="Optional minimum same-period QQQ annualized excess return, e.g. 0.10",
    )
    run_parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help='JSON parameter domain, e.g. \'{"name":"indicators.fast.period","values":[5,10]}\'',
    )
    run_parser.add_argument(
        "--series-data",
        type=Path,
        help="Optional external series Parquet containing macro/rate/benchmark observations",
    )
    run_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    repeat_parser = subparsers.add_parser(
        "repeat-research", help="Repeat bounded paper-only strategy backtests"
    )
    repeat_parser.add_argument("--source", type=Path, required=True)
    repeat_parser.add_argument("--data", type=Path, required=True)
    repeat_parser.add_argument("--series-data", type=Path)
    repeat_parser.add_argument("--method", choices=("grid", "random", "bayesian"), default="grid")
    repeat_parser.add_argument("--count", type=int, default=1)
    repeat_parser.add_argument("--seed", type=int, default=0)
    repeat_parser.add_argument("--min-trades", type=int, default=10)
    repeat_parser.add_argument("--min-annual-trades", type=int, default=30)
    repeat_parser.add_argument("--min-qqq-cagr", type=float)
    repeat_parser.add_argument("--generations", type=int, required=True)
    repeat_parser.add_argument("--interval-seconds", type=float, default=0.0)
    repeat_parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help='JSON parameter domain, e.g. \'{"name":"indicators.fast.period","values":[5,10]}\'',
    )
    repeat_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    autoresearch_parser = subparsers.add_parser(
        "autoresearch", help="Run bounded Codex-directed, paper-only strategy research"
    )
    autoresearch_parser.add_argument("--source", type=Path, required=True)
    autoresearch_parser.add_argument("--data", type=Path, required=True)
    autoresearch_parser.add_argument("--series-data", type=Path)
    autoresearch_parser.add_argument(
        "--method", choices=("grid", "random", "bayesian"), default="random"
    )
    autoresearch_parser.add_argument("--count", type=int, default=8)
    autoresearch_parser.add_argument("--seed", type=int, default=0)
    autoresearch_parser.add_argument("--min-trades", type=int, default=10)
    autoresearch_parser.add_argument("--min-annual-trades", type=int, default=30)
    autoresearch_parser.add_argument("--min-qqq-cagr", type=float)
    autoresearch_parser.add_argument("--generations", type=int, required=True)
    autoresearch_parser.add_argument("--interval-seconds", type=float, default=0.0)
    autoresearch_parser.add_argument("--domain", action="append", default=[])
    autoresearch_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    autoresearch_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    autoresearch_parser.add_argument("--project-root", type=Path, default=Path("."))
    terminal_parser = subparsers.add_parser(
        "terminal", help="Open the Codex chat and bounded autoresearch terminal"
    )
    terminal_parser.add_argument(
        "--mode", choices=("chat", "autoresearch", "direct-edit"), default="chat"
    )
    terminal_parser.add_argument("--prompt")
    terminal_parser.add_argument("--source", type=Path)
    terminal_parser.add_argument("--data", type=Path)
    terminal_parser.add_argument("--series-data", type=Path)
    terminal_parser.add_argument("--iterations", "--generations", dest="generations", type=int)
    terminal_parser.add_argument("--count", type=int, default=8)
    terminal_parser.add_argument("--seed", type=int, default=0)
    terminal_parser.add_argument("--min-trades", type=int, default=10)
    terminal_parser.add_argument("--min-annual-trades", type=int, default=30)
    terminal_parser.add_argument("--min-qqq-cagr", type=float)
    terminal_parser.add_argument("--interval-seconds", type=float, default=0.0)
    terminal_parser.add_argument("--domain", action="append", default=[])
    terminal_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    terminal_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    terminal_parser.add_argument("--project-root", type=Path, default=Path("."))
    terminal_parser.add_argument("--confirm-direct-edit", action="store_true")
    terminal_parser.add_argument("--worktree", type=Path)
    for command in ("resume", "rebuild-cache"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    cache_parser = subparsers.choices["rebuild-cache"]
    cache_parser.add_argument("--manifest-dir", type=Path, default=Path("manifests"))
    paper_parser = subparsers.add_parser("promote-paper")
    paper_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    paper_parser.add_argument("--champion-hash", required=True)
    paper_parser.add_argument("--expires-at", required=True)
    paper_parser.add_argument("--validated", action="store_true")
    approval_parser = subparsers.add_parser("request-live-approval")
    approval_parser.add_argument("--champion-hash", required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--file", type=Path, default=Path("state/audit.jsonl"))
    return parser


def _run_terminal_repl(args: argparse.Namespace) -> int:
    mode = args.mode
    print(terminal_help())
    while True:
        try:
            line = input("quant> ")
        except EOFError:
            return 0
        try:
            command = parse_terminal_command(line)
            if command.name == "exit":
                return 0
            if command.name == "help":
                print(terminal_help())
                continue
            if command.name == "mode":
                validate_direct_edit_gate(
                    mode=command.arguments[0],
                    confirmed=args.confirm_direct_edit,
                    worktree=args.worktree,
                    project_root=args.project_root,
                )
                mode = command.arguments[0]
                print(json.dumps({"status": "MODE_CHANGED", "mode": mode}, ensure_ascii=False))
                continue
            if command.name == "status":
                snapshot = DashboardStateReader(args.state_dir).read()
                print(json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False))
                continue
            if command.name == "stop":
                print(json.dumps({"status": "STOP_REQUESTED", "orders_enabled": False}))
                continue
            if command.name == "chat":
                chat_provider = CodexChatProvider.from_env(
                    args.env_file, workdir=args.project_root
                )
                print(chat_provider.ask(command.arguments[0]))
                continue
            if command.name == "research":
                if mode != "autoresearch":
                    raise ValueError("switch to autoresearch mode before /research")
                if args.source is None or args.data is None:
                    raise ValueError("terminal research requires --source and --data")
                research_provider = CodexExecProvider.from_env(
                    args.env_file,
                    workdir=args.project_root,
                    status_path=args.state_dir / "llm" / "status.json",
                )
                result = run_autoresearch(
                    ResearchLoopConfig(
                        project_root=args.project_root,
                        state_dir=args.state_dir,
                        source_path=str(args.source),
                        data_path=str(args.data),
                        series_data_path=str(args.series_data) if args.series_data else None,
                        method="random",
                        count=args.count,
                        seed=args.seed,
                        min_trades=args.min_trades,
                        min_annual_trades=args.min_annual_trades,
                        min_qqq_cagr_delta=args.min_qqq_cagr,
                        parameter_domains=parse_parameter_domains(
                            [json.loads(document) for document in args.domain]
                        ),
                        generations=int(command.arguments[0]),
                        interval_seconds=args.interval_seconds,
                    ),
                    ResearchDirector(research_provider),
                )
                print(json.dumps(result, ensure_ascii=False))
                continue
            raise ValueError(f"terminal command is not available in REPL: {command.name}")
        except (OSError, PermissionError, TypeError, ValueError) as exc:
            print(json.dumps({"status": "ERROR", "reason": str(exc)}, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_commands = {"init", "status", "resume", "promote-paper", "mode", "set-mode"}
    store = StateFileStore(args.state_dir) if args.command in state_commands else None
    if args.command == "init":
        assert store is not None
        store.write("champion", {"schema_version": 1, "status": "EMPTY", "champion": None})
        store.write("frontier", {"schema_version": 1, "families": {}})
        store.write(
            "knowledge",
            {
                "schema_version": 1,
                "known_good": [],
                "known_bad": [],
                "interactions": [],
                "unexplored": [],
            },
        )
        store.write("rescue_pool", {"schema_version": 1, "entries": []})
        store.write(
            "mode",
            {
                "schema_version": 1,
                "selected_mode": "paper",
                "orders_enabled": False,
                "requested_by": "initialization",
            },
        )
        print(json.dumps({"status": "INITIALIZED", "state_dir": str(args.state_dir)}))
        return 0
    if args.command == "list-features":
        print(
            json.dumps(
                {
                    "status": "OK",
                    "features": [
                        {
                            "name": spec.name,
                            "family": spec.family,
                            "inputs": list(spec.inputs),
                            "calculator": spec.calculator,
                            "lookback": spec.lookback,
                            "timeframe": spec.timeframe,
                        }
                        for spec in research_feature_specs()
                    ],
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "research-intent":
        snapshot = DashboardStateReader(args.state_dir).read()
        context = sanitize_context(
            {
                "generation": snapshot.strategy.generation or 0,
                "champion": snapshot.strategy.model_dump(mode="json"),
                "frontier": [],
                "observations": [
                    item.model_dump(mode="json") for item in snapshot.tests[:20]
                ],
                "feature_catalog": [
                    {
                        "name": spec.name,
                        "family": spec.family,
                        "inputs": list(spec.inputs),
                        "calculator": spec.calculator,
                        "lookback": spec.lookback,
                        "timeframe": spec.timeframe,
                    }
                    for spec in research_feature_specs()
                ],
            }
        )
        if not isinstance(context, dict):
            raise ValueError("research context must be an object")
        provider = CodexExecProvider.from_env(
            args.env_file,
            workdir=args.project_root,
            status_path=args.state_dir / "llm" / "status.json",
        )
        intent = ResearchDirector(provider).propose(context)
        record_intent(args.state_dir / "llm" / "intents.jsonl", intent)
        print(
            json.dumps(
                {
                    "status": "VALIDATED",
                    "intent": intent.model_dump(mode="json", exclude_none=True),
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command == "dashboard":
        run_dashboard(
            state_dir=args.state_dir,
            env_path=args.env_file,
            host=args.host,
            port=args.port,
        )
        return 0
    if args.command == "paper-order-smoke":
        if not args.confirm_paper_order:
            print(
                json.dumps(
                    {
                        "status": "CONFIRMATION_REQUIRED",
                        "reason": "pass --confirm-paper-order for the one-shot paper order",
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        try:
            config = PaperKISConfig.from_env(args.env_file)
            client = KISPaperOrderClient(config)
            paper_result = client.run_buy_then_sell(
                args.symbol,
                quantity=args.quantity,
                exchange=args.exchange,
                timeout_seconds=args.timeout_seconds,
                poll_seconds=args.poll_seconds,
            )
            paper_payload = {
                "status": paper_result.status,
                "mode": "paper",
                "symbol": paper_result.buy.symbol,
                "exchange": paper_result.buy.exchange,
                "requested_quantity": paper_result.buy.requested_quantity,
                "buy": {
                    "order_id": paper_result.buy.order_id,
                    "side": paper_result.buy.side,
                    "requested_quantity": paper_result.buy.requested_quantity,
                },
                "filled_buy_quantity": paper_result.filled_buy_quantity,
                "sell": (
                    {
                        "order_id": paper_result.sell.order_id,
                        "side": paper_result.sell.side,
                        "requested_quantity": paper_result.sell.requested_quantity,
                    }
                    if paper_result.sell is not None
                    else None
                ),
                "filled_sell_quantity": paper_result.filled_sell_quantity,
                "final_position_quantity": paper_result.final_position_quantity,
            }
            print(json.dumps(paper_payload, ensure_ascii=False))
            return 0 if paper_result.status == "FLAT" else 2
        except (KISConfigError, KISAPIError, PaperOrderError, ValueError, OSError) as exc:
            print(
                json.dumps(
                    {"status": "ERROR", "mode": "paper", "reason": str(exc)},
                    ensure_ascii=False,
                )
            )
            return 2
    if args.command == "import-strategies":
        if args.repo:
            source = parse_github_source(args.repo, ref=args.ref)
            summary = import_local_source(
                Path("."),
                strategies_dir=args.strategies_dir,
                source_origin=source.repository_url,
                github_source=source,
                dry_run=args.dry_run,
                kis_presets=args.kis_presets,
                clone_manager=CloneManager(),
            )
        else:
            summary = import_local_source(
                args.source,
                strategies_dir=args.strategies_dir,
                dry_run=args.dry_run,
                kis_presets=args.kis_presets,
            )
        print(json.dumps(summary.as_dict(), ensure_ascii=False, default=str))
        return 0
    if args.command in {"dashboard-status", "dashboard-refresh"}:
        service = DashboardService.from_environment(args.state_dir, args.env_file)
        snapshot = service.refresh() if args.command == "dashboard-refresh" else service.snapshot()
        health = snapshot.health
        print(
            json.dumps(
                {
                    "status": health.status if health else "UNKNOWN",
                    "effective_mode": snapshot.mode.effective_mode,
                    "live_enabled": snapshot.mode.live_enabled,
                    "kis_status": health.kis_status if health else "UNKNOWN",
                    "warning_codes": snapshot.warning_codes,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.command in {"import-strategy", "validate-strategy"}:
        result = normalize_source(args.source)
        payload: dict[str, object] = {
            "status": result.status.value,
            "source_hash": result.source_hash,
            "source_type": result.source_type,
            "reason": result.reason,
        }
        if result.strategy is not None:
            payload["strategy_id"] = result.strategy.strategy_id
            payload["strategy_hash"] = content_hash(
                result.strategy.model_dump(mode="json", by_alias=True)
            )
        if args.command == "validate-strategy" and result.status is ImportStatus.NORMALIZED:
            payload["status"] = "VALID"
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if result.status is ImportStatus.NORMALIZED else 2
    if args.command == "plan-generation":
        plan = plan_experiment(
            parent_ids=tuple(args.parents),
            structure_operations=(),
            parameter_domains=(),
            method=args.method,
            count=args.count,
            seed=args.seed,
        )
        print(
            json.dumps(
                {
                    "parent_ids": list(plan.parent_ids),
                    "method": plan.method,
                    "count": plan.count,
                    "seed": plan.seed,
                }
            )
        )
        return 0
    if args.command == "run-generation":
        domain_documents = [json.loads(document) for document in args.domain]
        evaluation_result = run_local_evaluation(
            project_root=Path("."),
            state_dir=args.state_dir,
            source_path=args.source,
            data_path=args.data,
            method=args.method,
            count=args.count,
            seed=args.seed,
            min_trades=args.min_trades,
            min_annual_trades=args.min_annual_trades,
            parameter_domains=parse_parameter_domains(domain_documents),
            series_data_path=args.series_data,
            min_qqq_cagr_delta=args.min_qqq_cagr,
        )
        print(json.dumps(evaluation_result, ensure_ascii=False))
        return 0
    if args.command == "repeat-research":
        repeat_result = run_repeated_evaluation(
            ResearchLoopConfig(
                project_root=Path("."),
                state_dir=args.state_dir,
                source_path=str(args.source),
                data_path=str(args.data),
                method=args.method,
                count=args.count,
                seed=args.seed,
                min_trades=args.min_trades,
                min_annual_trades=args.min_annual_trades,
                min_qqq_cagr_delta=args.min_qqq_cagr,
                series_data_path=str(args.series_data) if args.series_data else None,
                parameter_domains=parse_parameter_domains(
                    [json.loads(document) for document in args.domain]
                ),
                generations=args.generations,
                interval_seconds=args.interval_seconds,
            )
        )
        print(json.dumps(repeat_result, ensure_ascii=False))
        return 0
    if args.command == "autoresearch":
        autoresearch_provider = CodexExecProvider.from_env(
            args.env_file,
            workdir=args.project_root,
            status_path=args.state_dir / "llm" / "status.json",
        )
        autoresearch_result = run_autoresearch(
            ResearchLoopConfig(
                project_root=args.project_root,
                state_dir=args.state_dir,
                source_path=str(args.source),
                data_path=str(args.data),
                method=args.method,
                count=args.count,
                seed=args.seed,
                min_trades=args.min_trades,
                min_annual_trades=args.min_annual_trades,
                min_qqq_cagr_delta=args.min_qqq_cagr,
                series_data_path=str(args.series_data) if args.series_data else None,
                parameter_domains=parse_parameter_domains(
                    [json.loads(document) for document in args.domain]
                ),
                generations=args.generations,
                interval_seconds=args.interval_seconds,
            ),
            ResearchDirector(autoresearch_provider),
        )
        print(json.dumps(autoresearch_result, ensure_ascii=False))
        return 0
    if args.command == "terminal":
        validate_direct_edit_gate(
            mode=args.mode,
            confirmed=args.confirm_direct_edit,
            worktree=args.worktree,
            project_root=args.project_root,
        )
        if args.prompt:
            if args.mode != "chat":
                raise ValueError("--prompt mode is available only in chat mode")
            chat_provider = CodexChatProvider.from_env(
                args.env_file, workdir=args.project_root
            )
            print(chat_provider.ask(args.prompt))
            return 0
        return _run_terminal_repl(args)
    if args.command == "resume":
        assert store is not None
        champion = store.read("champion").payload
        print(json.dumps({"status": "RESUME_READY", "champion": champion["status"]}))
        return 0
    if args.command == "set-mode":
        assert store is not None
        payload = {
            "schema_version": 1,
            "selected_mode": args.mode,
            "orders_enabled": False,
            "requested_by": "user",
        }
        store.write("mode", payload)
        print(json.dumps({"status": "MODE_SELECTED", **payload}))
        return 0
    if args.command == "mode":
        assert store is not None
        print(json.dumps(store.read("mode").payload, ensure_ascii=False))
        return 0
    if args.command == "rebuild-cache":
        manifests = sorted(args.manifest_dir.glob("*.json")) if args.manifest_dir.is_dir() else []
        valid = 0
        for manifest in manifests:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("experiment_hash"):
                valid += 1
        print(json.dumps({"status": "REBUILT", "validated_manifests": valid}))
        return 0
    if args.command == "promote-paper":
        assert store is not None
        champion = store.read("champion").payload
        if champion.get("champion_hash") != args.champion_hash:
            raise PermissionError("paper champion hash does not match")
        if not args.validated:
            raise PermissionError("paper validation is required")
        expires_at = datetime.fromisoformat(args.expires_at)
        if expires_at.tzinfo is None:
            raise ValueError("expires-at must include timezone")
        store.write(
            "paper",
            {
                "status": "ENABLED",
                "champion_hash": args.champion_hash,
                "expires_at": args.expires_at,
            },
        )
        print(json.dumps({"status": "PAPER_ENABLED", "champion_hash": args.champion_hash}))
        return 0
    if args.command == "request-live-approval":
        print(
            json.dumps(
                {
                    "status": "BLOCKED_EXTERNAL_APPROVAL",
                    "champion_hash": args.champion_hash,
                    "reason": (
                        "live approval requires a separate human-controlled deployment process"
                    ),
                }
            )
        )
        return 3
    if args.command == "audit":
        records = []
        if args.file.is_file():
            records = [
                json.loads(line) for line in args.file.read_text(encoding="utf-8").splitlines()
            ]
        print(json.dumps({"status": "OK", "records": len(records)}))
        return 0
    assert store is not None
    champion = store.read("champion").payload
    frontier = store.read("frontier").payload
    print(
        json.dumps(
            {"champion": champion["status"], "frontier_families": len(frontier["families"])}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
