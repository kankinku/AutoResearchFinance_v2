from __future__ import annotations

from integrations import codex_mcp_core as _core
from integrations.codex_mcp_manual_adapter import (
    ManualCodexMCPServer,
    create_manual_mcp_server,
)
from integrations.codex_mcp_sdk_server import main as _sdk_main

# Compatibility imports retained for existing tests/internal consumers.
# Runtime execution through this module is still the official SDK entrypoint.
CodexMCPServer = ManualCodexMCPServer
_PUBLIC_TOOL_PLANES = _core._PUBLIC_TOOL_PLANES
_TARGET_PUBLIC_TOOL_NAMES = _core._TARGET_PUBLIC_TOOL_NAMES
_all_tools = _core._all_tools
_system_config = _core._system_config
_system_schema = _core._system_schema
_tools = _core._tools
_with_legacy_compatibility = _core._with_legacy_compatibility
_with_public_contract = _core._with_public_contract
create_mcp_server = create_manual_mcp_server

MCP_TRANSPORT = "official_sdk"


def main(argv: list[str] | None = None) -> int:
    return _sdk_main(argv, prog="quant-autoresearch-codex-mcp")


if __name__ == "__main__":
    raise SystemExit(main())
