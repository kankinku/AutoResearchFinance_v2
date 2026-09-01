from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from core.data.parquet import ParquetDataProvider
from core.features.registry import default_feature_registry
from core.integrity.hashes import content_hash
from dashboard.run import run_dashboard
from dashboard.service import DashboardService
from evaluation.selector import FunnelConfig
from experiments.planner import plan_experiment
from memory.state_files import StateFileStore
from orchestration.pipeline import GenerationPipeline
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
    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    dashboard_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    dashboard_parser.add_argument("--host", default="127.0.0.1")
    dashboard_parser.add_argument("--port", type=int, default=8080)
    for command in ("dashboard-status", "dashboard-refresh"):
        dashboard_command = subparsers.add_parser(command)
        dashboard_command.add_argument("--state-dir", type=Path, default=Path("state"))
        dashboard_command.add_argument("--env-file", type=Path, default=Path(".env"))
    subparsers.choices["set-mode"].add_argument(
        "--mode", choices=("paper", "live"), required=True
    )
    for command in ("import-strategy", "validate-strategy"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--source", type=Path, required=True)
    plan_parser = subparsers.add_parser("plan-generation")
    plan_parser.add_argument("--parent", action="append", required=True, dest="parents")
    plan_parser.add_argument(
        "--method", choices=("grid", "random", "bayesian"), required=True
    )
    plan_parser.add_argument("--count", type=int, required=True)
    plan_parser.add_argument("--seed", type=int, required=True)
    run_parser = subparsers.add_parser("run-generation")
    run_parser.add_argument("--source", type=Path, required=True)
    run_parser.add_argument("--data", type=Path, required=True)
    run_parser.add_argument("--method", choices=("grid", "random", "bayesian"), default="grid")
    run_parser.add_argument("--count", type=int, default=1)
    run_parser.add_argument("--seed", type=int, default=0)
    run_parser.add_argument("--min-trades", type=int, default=10)
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
                        for spec in default_feature_registry().all()
                    ],
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
        imported = normalize_source(args.source)
        if imported.strategy is None:
            print(json.dumps({"status": "UNSUPPORTED", "reason": imported.reason}))
            return 2
        pipeline_result = GenerationPipeline().run(
            parent=imported.strategy,
            dataset=ParquetDataProvider.read(args.data),
            operations=(),
            domains=(),
            method=args.method,
            count=args.count,
            seed=args.seed,
            funnel=FunnelConfig(
                min_fast_trades=args.min_trades,
                min_full_trades=args.min_trades,
            ),
        )
        print(
            json.dumps(
                {
                    "status": "COMPLETED",
                    "candidate_count": len(pipeline_result.candidates),
                    "counts": {
                        status: sum(item.status == status for item in pipeline_result.funnel)
                        for status in sorted({item.status for item in pipeline_result.funnel})
                    },
                }
            )
        )
        return 0
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
