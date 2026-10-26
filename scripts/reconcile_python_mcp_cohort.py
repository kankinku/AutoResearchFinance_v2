"""Inspect the old Codex study without modifying the original evidence log."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from application.python_mcp_checkpoint_reconciliation import reconcile_python_mcp_cohort


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Quant checkpoint reconciliation")
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    result = reconcile_python_mcp_cohort(Path.cwd(), args.work)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
