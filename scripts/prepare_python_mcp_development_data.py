"""One-time, read-only-from-source development snapshot importer.

Run from the PythonMCP repository root. Never touches protected core or OOS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from application.python_mcp_development_data import import_pinned_development_data


def main() -> int:
    parser = argparse.ArgumentParser(description='Pin existing real QQQ development data')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    result = import_pinned_development_data(Path.cwd(), args.source, args.manifest)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
