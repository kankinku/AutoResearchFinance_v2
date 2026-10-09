"""Run the isolated GPT research MCP over official stdio, for Secure MCP Tunnel.

Only tool frames go to stdout. This process binds no TCP ports and requires no
ChatGPT-specific local bearer token; outbound tunnel authentication is separate.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChatGPT-specific research MCP stdio")
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    args = parser.parse_args(argv)
    adapter = create_chatgpt_sdk_adapter(
        project_root=args.project_root.resolve(),
        state_dir=args.state_dir.resolve(),
    )
    asyncio.run(adapter.serve_stdio())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
