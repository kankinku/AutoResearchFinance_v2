from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server

SDK_ADAPTER_STATUS = "SHADOW_SKELETON"
_SERVER_NAME = "quant-autoresearch"
_SERVER_VERSION = "0.1.0"


@dataclass(frozen=True)
class SDKMCPServerAdapter:
    """Official-SDK transport skeleton kept separate from the canonical manual adapter."""

    state_dir: Path
    project_root: Path
    server: Server[Any]

    async def serve_stdio(self) -> None:
        """Serve the shadow SDK adapter over stdio.

        Tool list/call parity is intentionally deferred to Phase 5.3. Until then the
        canonical entrypoint remains integrations.codex_mcp_server.
        """

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


def create_sdk_mcp_server(*, state_dir: Path, project_root: Path) -> SDKMCPServerAdapter:
    state = state_dir.resolve()
    root = project_root.resolve()
    server: Server[Any] = Server(
        _SERVER_NAME,
        version=_SERVER_VERSION,
        description=(
            "Shadow official-SDK adapter for quant-autoresearch. "
            "Tool parity is added before canonical cutover."
        ),
    )
    return SDKMCPServerAdapter(
        state_dir=state,
        project_root=root,
        server=server,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-autoresearch-sdk-shadow")
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    adapter = create_sdk_mcp_server(
        state_dir=args.state_dir,
        project_root=args.project_root,
    )
    asyncio.run(adapter.serve_stdio())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
