from __future__ import annotations

import argparse
import subprocess


def build_tag_command(champion_hash: str, generation: int) -> list[str]:
    if not champion_hash or generation < 0:
        raise ValueError("champion hash and non-negative generation are required")
    return ["git", "tag", f"champion/g{generation:04d}-{champion_hash[:12]}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--champion-hash", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    command = build_tag_command(args.champion_hash, args.generation)
    print(" ".join(command))
    if args.apply:
        subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
