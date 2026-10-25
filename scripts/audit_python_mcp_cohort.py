"""Read-only evidence audit; prints no raw strategy plans or account secrets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from application.python_mcp_research_audit import audit_python_mcp_cohort


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit isolated model-authored development study")
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    report = audit_python_mcp_cohort(Path.cwd(), args.work)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
