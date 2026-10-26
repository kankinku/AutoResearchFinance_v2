from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any, cast

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

from application.market_data_service import MarketDataError
from integrations.codex_mcp_core import (
    CodexMCPServer,
    _tools,
    _with_legacy_compatibility,
    _with_public_contract,
)
from integrations.codex_mcp_payload import text_content_payload
from research.llm.gpt_context import write_provider_status

SDK_ADAPTER_STATUS = "CANONICAL_SDK"
_SERVER_NAME = "quant-autoresearch"
_SERVER_VERSION = "0.1.0"


_ACADEMIC_CHECKPOINT_TOOLS = frozenset(
    {
        "start_algorithm_research",
        "get_algorithm_research",
        "submit_algorithm_plan",
        "submit_algorithm_diagnosis",
        "evaluate_algorithm_experiments",
        "resume_algorithm_research",
        "cancel_algorithm_research",
        "reconcile_algorithm_research",
    }
)

# Static, audited messages only: NEVER expose exception text, raw input,
# checkpoint tokens, OAuth context, private paths, or full model proposals.
_SAFE_ACADEMIC_REPAIR_MESSAGES = {
    "INHERITED_FEATURE_BINDING_MISSING": (
        "A newly declared feature has no canonical costed replay vector in "
        "this inherited session. No generation was consumed. Retry the same "
        "checkpoint with existing audited feature aliases; independent new "
        "feature replay support requires a separately verified compiler."
    ),
    "INTENT_PATH_TARGET": (
        "Invalid typed rule target. ADD_RULE needs entry.conditions or "
        "exit.conditions; REPLACE_RULE requires an indexed condition. "
        "Correct the operation and retry the same untouched checkpoint."
    ),
    "UNCHANGED_CANONICAL_FILLS": (
        "Candidate produced identical canonical fills and costed equity. "
        "Revise the executable signal or risk rule, then retry the same checkpoint."
    ),
    "DUPLICATE_SEMANTIC_PLAN": (
        "An existing generation has the same plan semantics; propose a distinct "
        "entry/regime hypothesis and retry the same checkpoint."
    ),
    "DUPLICATE_EFFECTIVE_SIGNALS": (
        "The new plan has the same effective signals as an existing generation. "
        "Revise entry or regime conditions before retrying the checkpoint."
    ),
    "DUPLICATE_EFFECTIVE_INHERITED_SIGNALS": (
        "An existing generation has the same inherited entry/exit/regime signals. "
        "Propose a different executable mutation and retry the checkpoint."
    ),
    "DUPLICATE_INHERITED_STRATEGY": (
        "The inherited strategy is already present in the audited lineage. "
        "Use a different validated mutation at the same checkpoint."
    ),
    "P2_PRECOMMIT_RISK_REJECTED": (
        "Costed parent-child risk gate rejected this proposal. Revise the "
        "child without weakening risk limits and retry the same checkpoint."
    ),
    "P3_SEMANTIC_PREFLIGHT_REJECTED": (
        "The submitted mutation has no effective semantic change. "
        "Revise the operation and retry the same checkpoint."
    ),
    "P3_DIAGNOSIS_SEMANTIC_REJECTED": (
        "The proposed next research intent is redundant on the audited signals. "
        "Revise the diagnosis at the same checkpoint without weakening quality gates."
    ),
}


def _safe_academic_checkpoint_error(exc: Exception) -> dict[str, object]:
    """Return an allowlisted model-repair signal, never arbitrary exception details."""
    signal = getattr(exc, "code", None)
    if signal not in _SAFE_ACADEMIC_REPAIR_MESSAGES:
        # Inspect ONLY fixed public discriminator prefixes. Raw text is never returned.
        problem = str(exc) if isinstance(exc, ValueError) else ""
        signal = next(
            (code for code in _SAFE_ACADEMIC_REPAIR_MESSAGES if problem.startswith(code + ":")),
            None,
        )
    if signal in _SAFE_ACADEMIC_REPAIR_MESSAGES:
        return {
            "status": "ERROR",
            "error_code": signal,
            "message": _SAFE_ACADEMIC_REPAIR_MESSAGES[signal],
            "retry_same_checkpoint": True,
            "orders_enabled": False,
            "recovery": {
                "next_step": "READ_CURRENT_CHECKPOINT_THEN_REVISE",
                "tool": "get_algorithm_research",
                "response_mode": "compact",
                "never_reuse_stale_checkpoint_token": True,
            },
        }
    return {
        "status": "ERROR",
        "error_code": "ACADEMIC_CHECKPOINT_REJECTED",
        "message": "Academic checkpoint request rejected. Inspect current session "
        "before retrying; internal failure details are withheld.",
        "retry_same_checkpoint": False,
        "orders_enabled": False,
        "recovery": {
            "next_step": "READ_CURRENT_CHECKPOINT_STOP_IF_UNCERTAIN",
            "tool": "get_algorithm_research",
            "response_mode": "full",
            "never_reuse_stale_checkpoint_token": True,
        },
    }


class SDKMCPServerAdapter:
    """Official-SDK adapter sharing the canonical MCP application dispatch."""

    def __init__(self, *, state_dir: Path, project_root: Path) -> None:
        self.state_dir = state_dir.resolve()
        self.project_root = project_root.resolve()
        self.dispatcher = CodexMCPServer(
            state_dir=self.state_dir,
            project_root=self.project_root,
        )
        self.server: Server[Any] = Server(
            _SERVER_NAME,
            version=_SERVER_VERSION,
            description=(
                "Official-SDK adapter for quant-autoresearch. "
                "Tool schema and dispatch parity are preserved after canonical cutover."
            ),
            on_list_tools=self.list_tools,
            on_call_tool=self.call_tool,
        )

    async def list_tools(
        self,
        _context: ServerRequestContext[Any],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        write_provider_status(
            self.state_dir / "llm" / "status.json",
            "gpt_mcp",
            "ONLINE",
            "MCP_CONNECTED",
        )
        return types.ListToolsResult(
            tools=[_sdk_tool(tool) for tool in _tools()],
        )

    async def call_tool(
        self,
        _context: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        arguments = params.arguments or {}
        try:
            payload = self.dispatcher._dispatch(params.name, dict(arguments))
            payload = _with_legacy_compatibility(params.name, payload)
            payload = _with_public_contract(params.name, payload)
        except (OSError, PermissionError, TypeError, ValueError) as exc:
            if params.name in _ACADEMIC_CHECKPOINT_TOOLS:
                return _sdk_tool_result(
                    _safe_academic_checkpoint_error(exc),
                    is_error=True,
                )
            if isinstance(exc, MarketDataError) and params.name in {
                "list_market_data",
                "download_market_data",
                "validate_market_data",
            }:
                return _sdk_tool_result(
                    {
                        "status": "ERROR",
                        "error_code": exc.code,
                        "message": str(exc),
                        "orders_enabled": False,
                    },
                    is_error=True,
                )
            if params.name in {
                "preflight_research_batch",
                "start_research_batch",
                "get_research_batch_status",
                "get_research_batch_report",
                "cancel_research_batch",
                "resume_research_batch",
            }:
                code = getattr(exc, "code", None)
                if not isinstance(code, str):
                    code = (
                        "NO_BATCH_FOUND"
                        if isinstance(exc, ValueError) and str(exc) == "research batch not found"
                        else "INVALID_RESEARCH_INPUTS"
                    )
                message = {
                    "DATA_FILE_NOT_FOUND": "No Parquet market data at data_path. "
                    "Check research_inputs in get_research_brief.",
                    "SOURCE_FILE_NOT_FOUND": "Strategy source_path does not exist. "
                    "Check research_inputs in get_research_brief.",
                    "PARENT_ID_MISMATCH": "intent.parent_ids does not match source "
                    "strategy_id; check get_research_brief.",
                    "NO_BATCH_FOUND": "No accepted research batch exists yet.",
                    "BATCH_NOT_INTERRUPTED": (
                        "Batch is not interrupted; it may already be completed or still running. "
                        "Read get_research_batch_status before requesting resume."
                    ),
                    "CHECKPOINT_MISSING": (
                        "No safely verified completed checkpoint exists. Do not rerun "
                        "the interrupted generation; investigate its Evidence."
                    ),
                    "CHECKPOINT_MISMATCH": (
                        "Committed generation history or checkpoint is inconsistent. "
                        "Review immutable Evidence before any continuation."
                    ),
                    "CHECKPOINT_INPUT_CHANGED": (
                        "Research inputs changed after the original run. "
                        "The interrupted batch cannot be safely resumed."
                    ),
                    "WORKER_STILL_ALIVE": (
                        "The original worker is still alive; do not launch a second worker."
                    ),
                    "OTHER_BATCH_ACTIVE": (
                        "Another batch is active. Do not start concurrent research."
                    ),
                }.get(code, "Check source_path, data_path, ResearchIntent and input permissions.")
                return _sdk_tool_result(
                    {
                        "status": "ERROR",
                        "error_code": code,
                        "message": message,
                        "orders_enabled": False,
                    },
                    is_error=True,
                )
            if params.name in {
                "start_guided_research",
                "get_guided_research",
                "submit_guided_generation",
                "reconcile_guided_research",
            }:
                duplicate = isinstance(exc, ValueError) and "DUPLICATE_STRATEGY" in str(exc)
                return _sdk_tool_result(
                    {
                        "status": "ERROR",
                        "error_code": (
                            "DUPLICATE_STRATEGY" if duplicate else "GUIDED_RESEARCH_REJECTED"
                        ),
                        "message": (
                            "Strategy already evaluated in this session; submit a genuinely "
                            "different executable hypothesis using the same checkpoint."
                            if duplicate
                            else "Guided research request rejected; inspect the active checkpoint "
                            "and registered strategy source. No automatic replay."
                        ),
                        "orders_enabled": False,
                    },
                    is_error=True,
                )
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"},
                is_error=True,
            )
        return _sdk_tool_result(payload, is_error=False)

    async def serve_stdio(self) -> None:
        """Serve the official SDK adapter over stdio."""

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


def create_sdk_mcp_server(*, state_dir: Path, project_root: Path) -> SDKMCPServerAdapter:
    return SDKMCPServerAdapter(
        state_dir=state_dir,
        project_root=project_root,
    )


def main(
    argv: list[str] | None = None,
    *,
    prog: str = "quant-autoresearch-sdk-shadow",
) -> int:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    adapter = create_sdk_mcp_server(
        state_dir=args.state_dir,
        project_root=args.project_root,
    )
    asyncio.run(adapter.serve_stdio())
    return 0


def _sdk_tool(definition: dict[str, object]) -> types.Tool:
    name = definition.get("name")
    description = definition.get("description")
    input_schema = definition.get("inputSchema")
    if not isinstance(name, str):
        raise TypeError("tool name must be a string")
    if description is not None and not isinstance(description, str):
        raise TypeError("tool description must be a string")
    if not isinstance(input_schema, dict):
        raise TypeError("tool inputSchema must be an object")
    return types.Tool(
        name=name,
        description=description,
        input_schema=cast(dict[str, Any], input_schema),
    )


def _sdk_tool_result(payload: object, *, is_error: bool) -> types.CallToolResult:
    content = text_content_payload(payload)
    text = content[0]["text"]
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        is_error=is_error,
    )


if __name__ == "__main__":
    raise SystemExit(main())
