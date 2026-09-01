from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def snapshot_payload(
    *, champion_hash: str, generation: int, frontier_hashes: tuple[str, ...]
) -> dict[str, Any]:
    if not champion_hash or generation < 0:
        raise ValueError("champion hash and non-negative generation are required")
    return {
        "schema_version": 1,
        "champion_hash": champion_hash,
        "generation": generation,
        "frontier_hashes": sorted(set(frontier_hashes)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--champion-hash", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--frontier-hash", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = snapshot_payload(
        champion_hash=args.champion_hash,
        generation=args.generation,
        frontier_hashes=tuple(args.frontier_hash),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
