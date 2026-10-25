"""Python-only read-only MCP client for the isolated Quant fork.

Moon is the hosting workspace, NOT this server. This module makes zero GPT
requests and cannot submit research plans, trade orders or API credentials.
Future authenticated model providers must be separate and explicit.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PUBLIC_READ_TOOLS = frozenset(
    {"get_workspace_status", "list_features", "get_algorithm_research"}
)


class ReadOnlyToolRejected(ValueError):
    """No write-capable MCP tool can be invoked by the Python probe."""


class QuantMCPResponseError(RuntimeError):
    """Quant responded with an unsuccessful or malformed MCP result."""


@dataclass(frozen=True)
class QuantMCPSettings:
    project_root: Path
    state_dir: Path
    scope_session: str | None = None
    surface: str = "codex"
    capture_public_key_hex: str | None = None
    python_executable: str = sys.executable

    def __post_init__(self) -> None:
        root = self.project_root.resolve()
        state = self.state_dir.resolve()
        if not root.is_dir():
            raise ValueError("project root must be an existing directory")
        if not state.is_relative_to(root / "state"):
            raise ValueError("MCP state must be inside the project's state/ directory")
        if self.surface not in ("codex", "chatgpt_academic"):
            raise ValueError("invalid MCP surface")
        if self.capture_public_key_hex is not None:
            if re.fullmatch(r"[0-9a-f]{64}", self.capture_public_key_hex) is None:
                raise ValueError("capture public key must be a 32-byte lowercase hex string")
            if self.surface != "chatgpt_academic" or self.scope_session is None:
                raise ValueError("capture public key requires an academic scoped session")
        if self.scope_session is not None and re.fullmatch(
            r"[0-9a-f]{32}", self.scope_session
        ) is None:
            raise ValueError("scope_session must contain 32 lowercase hex characters")
        object.__setattr__(self, "project_root", root)
        object.__setattr__(self, "state_dir", state)


class QuantMCPDirectClient:
    """Executes verified read-only Quant operations via an isolated child MCP."""

    def __init__(self, settings: QuantMCPSettings) -> None:
        self.settings = settings

    def require_read_only_tool(self, name: str) -> None:
        if name not in PUBLIC_READ_TOOLS:
            raise ReadOnlyToolRejected("MCP read-only policy rejects tool " + name)
        if name == "get_algorithm_research":
            if self.settings.surface != "chatgpt_academic":
                raise ReadOnlyToolRejected("research status requires ChatGPT academic MCP surface")
            if self.settings.scope_session is None:
                raise ReadOnlyToolRejected("research status requires an exact scoped session")

    def assert_session(self, session_id: str) -> None:
        if self.settings.scope_session != session_id:
            raise ValueError("MCP session mismatch: cross-session access denied")

    def _server_params(self) -> StdioServerParameters:
        """Do not inherit arbitrary tokens, other projects' OAuth or MCP policy."""
        environment = {
            name: os.environ[name]
            for name in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
            if name in os.environ
        }
        checkout = Path(__file__).resolve().parents[1]
        environment["PYTHONPATH"] = str(checkout)
        session = self.settings.scope_session
        if session is not None:
            # Enable only an explicitly selected existing fork-local P5-style
            # research session; do not enroll unknown sessions retroactively.
            for name in (
                "QUANT_MCP_PARENT_PORTFOLIO_V2_SESSION_ID",
                "QUANT_MCP_GENERALIZATION_PARENT_V1_SESSION_ID",
                "QUANT_MCP_P4_QUALITY_SESSION_ID",
                "QUANT_MCP_P4_S7_QUALITY_SESSION_ID",
            ):
                environment[name] = session
            if self.settings.capture_public_key_hex is not None:
                # Public key only. The private signing key remains external.
                environment["QUANT_MCP_P4_MODEL_CAPTURE_SESSION_ID"] = session
                environment["QUANT_MCP_P4_CAPTURE_PUBLIC_KEY_HEX"] = (
                    self.settings.capture_public_key_hex
                )
        return StdioServerParameters(
            command=self.settings.python_executable,
            args=[
                "-m", (
                    "integrations.chatgpt_mcp_stdio"
                    if self.settings.surface == "chatgpt_academic"
                    else "integrations.codex_mcp_server"
                ),
                "--project-root", str(self.settings.project_root),
                "--state-dir", str(self.settings.state_dir),
            ],
            env=environment,
            cwd=str(checkout),
        )

    @staticmethod
    def _validated_payload(
        response: Any, *, require_orders_disabled: bool = True
    ) -> dict[str, Any]:
        if response.is_error:
            raise QuantMCPResponseError("read-only MCP tool reported an error")
        value = response.structured_content
        if value is None:
            for block in response.content:
                if block.type == "text":
                    try:
                        value = json.loads(block.text)
                    except (json.JSONDecodeError, ValueError) as exc:
                        raise QuantMCPResponseError("MCP response is not JSON") from exc
                    break
        if not isinstance(value, dict):
            raise QuantMCPResponseError("MCP response must be a JSON object")
        if require_orders_disabled and value.get("orders_enabled") is not False:
            raise QuantMCPResponseError("orders disabled flag missing or unsafe")
        return value

    async def read_academic_checkpoint(self, session_id: str) -> dict[str, Any]:
        """Read the exact fork-local session; never submit or count a generation."""
        self.require_read_only_tool("get_algorithm_research")
        self.assert_session(session_id)
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            async with stdio_client(self._server_params()) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    advertised = {
                        item.name for item in (await session.list_tools()).tools
                    }
                    if "get_algorithm_research" not in advertised:
                        raise QuantMCPResponseError("academic read tool is unavailable")
                    result = self._validated_payload(
                        await session.call_tool(
                            "get_algorithm_research",
                            arguments={"session_id": session_id},
                        )
                    )
                    if result.get("session_id") != session_id:
                        raise QuantMCPResponseError("academic session identity mismatch")
                    if result.get("independent_oos_approved") is not False:
                        raise QuantMCPResponseError("independent OOS must remain sealed")
                    count = result.get("completed_generations")
                    if type(count) is not int or count < 0:
                        raise QuantMCPResponseError("invalid academic generation count")
                    return result

        except Exception as exc:
            # Python 3.10 compatibility: official MCP may raise a nested
            # exception group (3.11+); never mask unrelated transport errors.
            splitter = getattr(exc, "split", None)
            if callable(splitter):
                matching, unrelated = splitter(QuantMCPResponseError)
                if matching is not None and unrelated is None:
                    raise QuantMCPResponseError(
                        "academic MCP read rejected; inspect fork-local session"
                    ) from exc
            raise

    async def probe(self) -> dict[str, Any]:
        """Real MCP IO, purely local computation, never submits research."""
        self.require_read_only_tool("get_workspace_status")
        self.require_read_only_tool("list_features")
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)
        async with stdio_client(self._server_params()) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                declared = await session.list_tools()
                names = {item.name for item in declared.tools}
                if not {"get_workspace_status", "list_features"} <= names:
                    raise QuantMCPResponseError("required read-only tools unavailable")
                status = self._validated_payload(
                    await session.call_tool("get_workspace_status", arguments={})
                )
                feature_list = self._validated_payload(
                    await session.call_tool("list_features", arguments={}),
                    require_orders_disabled=False,
                )
                features = feature_list.get("features")
                count = (
                    len(features)
                    if isinstance(features, list)
                    else int(feature_list.get("feature_count", 0))
                )
                return {
                    "transport": "stdio",
                    "surface": self.settings.surface,
                    "server": "quant-autoresearch",
                    "host_role": "moon_workspace_only",
                    "model_calls": 0,
                    "orders_enabled": False,
                    "mcp_tool_count": len(names),
                    "quant_status": status.get("status", "MISSING"),
                    "feature_count": count,
                    "research_session": "UNSET_READ_ONLY",
                    "provenance": "DIRECT_PYTHON_MCP_NO_LLM",
                }
