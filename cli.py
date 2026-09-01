from __future__ import annotations

import argparse
import json
from pathlib import Path

from memory.state_files import StateFileStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant-autoresearch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "status"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--state-dir", type=Path, default=Path("state"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = StateFileStore(args.state_dir)
    if args.command == "init":
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
