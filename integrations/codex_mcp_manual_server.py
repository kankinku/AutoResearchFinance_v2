from __future__ import annotations

import argparse
import sys
from pathlib import Path

from integrations.codex_mcp_manual_adapter import create_manual_mcp_server
from integrations.codex_mcp_protocol import serve_lines

MCP_TRANSPORT = "manual_rollback"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-autoresearch-codex-mcp-manual")
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    serve_lines(
        create_manual_mcp_server(state_dir=args.state_dir, project_root=args.project_root),
        sys.stdin,
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
