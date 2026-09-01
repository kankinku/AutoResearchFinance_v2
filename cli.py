from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.integrity.hashes import content_hash
from experiments.planner import plan_experiment
from memory.state_files import StateFileStore
from strategy_ir.normalizer import ImportStatus, normalize_source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant-autoresearch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "status"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--state-dir", type=Path, default=Path("state"))
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = StateFileStore(args.state_dir) if args.command in {"init", "status"} else None
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
        print(json.dumps({"status": "INITIALIZED", "state_dir": str(args.state_dir)}))
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
