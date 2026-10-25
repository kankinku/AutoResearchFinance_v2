"""Read-only Python MCP probe for the isolated Quant fork.

Run using a Python environment containing the repository's MCP dependencies.
Moon hosts the process; the child server is Quant. No GPT model is called.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from integrations.python_mcp_direct import QuantMCPDirectClient, QuantMCPSettings


def main() -> int:
    checkout = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Probe fork-local Quant MCP without GPT")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=checkout / "state" / "python-mcp",
        help="State under this fork's state/ directory; never the source P5",
    )
    args = parser.parse_args()
    settings = QuantMCPSettings(project_root=checkout, state_dir=args.state_dir)
    result = asyncio.run(QuantMCPDirectClient(settings).probe())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
