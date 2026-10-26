"""Probe Quant MCP tool transport without model, strategy, or research writes.

A client/tool listing is NOT permission to drive ChatGPT host model turns.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from integrations.python_mcp_direct import QuantMCPDirectClient, QuantMCPSettings


async def _probe(root: Path, state: Path) -> dict[str, Any]:
    client = QuantMCPDirectClient(
        QuantMCPSettings(
            project_root=root,
            state_dir=state,
            surface="chatgpt_academic",
            python_executable=sys.executable,
        )
    )
    report = await client.probe()
    if report["mcp_tool_count"] != 32 or report["orders_enabled"] is not False:
        raise RuntimeError("Quant MCP surface or order guard changed unexpectedly")
    return {
        **report,
        "schema": "sdk-quant-host-dispatch-readonly-preflight-v1",
        "sdk_mcp_tool_client_available": True,
        "native_chatgpt_model_turn_dispatch_verified": False,
        "sdk_repeat_controller_status": "BLOCKED_MODEL_HOST_DISPATCH",
        "new_generations": 0,
        "real_provider_verified": False,
        "independent_oos_approved": False,
        "scope": "ISOLATED_MCP_STDIO_READ_ONLY_NOT_PRODUCTION_HOST",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(_probe(args.project_root.resolve(), args.state_dir.resolve()))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
