"""Isolated ChatGPT-facing MCP surface; legacy 13-tool public ABI stays frozen."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    ValidationError as JSONSchemaValidationError,
)
from mcp import types
from mcp.server import ServerRequestContext
from pydantic import Field, field_serializer

from application.mcp_contracts import PublicToolContractMetadata, PublicToolPlane
from application.research_batch_service import MAX_CANDIDATES, MAX_GENERATIONS
from integrations.codex_mcp_core import _chat_directed_step_schema, _tools
from integrations.codex_mcp_sdk_server import (
    SDKMCPServerAdapter,
    _sdk_tool,
    _sdk_tool_result,
)
from integrations.mcp_context_budget import (
    COMPACTABLE_TOOLS,
    append_context_metrics,
    compact_mcp_context,
    encoded_size,
)
from integrations.quant_mcp_diagnostics import MCPAuditLog

_CHATGPT_CANONICAL = frozenset(
    {
        "initialize_research_state",
        "get_workspace_status",
        "validate_strategy",
        "import_strategies",
        "list_strategies",
        "list_features",
        "get_research_evidence",
        "get_dashboard_status",
    }
)
_CHATGPT_CUSTOM: dict[str, PublicToolPlane] = {
    "get_research_brief": "EVIDENCE_STATUS",
    "start_algorithm_research": "EXECUTION_LIFECYCLE",
    "get_algorithm_research": "EVIDENCE_STATUS",
    "submit_algorithm_plan": "EXECUTION_LIFECYCLE",
    "submit_algorithm_diagnosis": "EXECUTION_LIFECYCLE",
    "resume_algorithm_research": "EXECUTION_LIFECYCLE",
    "cancel_algorithm_research": "EXECUTION_LIFECYCLE",
    "reconcile_algorithm_research": "EXECUTION_LIFECYCLE",
    "evaluate_algorithm_experiments": "EXECUTION_LIFECYCLE",
    "run_research_step": "EXECUTION_LIFECYCLE",
    "start_guided_research": "EXECUTION_LIFECYCLE",
    "get_guided_research": "EVIDENCE_STATUS",
    "reconcile_guided_research": "EXECUTION_LIFECYCLE",
    "submit_guided_generation": "EXECUTION_LIFECYCLE",
    "start_research_batch": "EXECUTION_LIFECYCLE",
    "preflight_research_batch": "CATALOG_VALIDATION",
    "get_research_batch_status": "EVIDENCE_STATUS",
    "get_research_batch_report": "EVIDENCE_STATUS",
    "cancel_research_batch": "EXECUTION_LIFECYCLE",
    "resume_research_batch": "EXECUTION_LIFECYCLE",
    "list_market_data": "EVIDENCE_STATUS",
    "validate_market_data": "CATALOG_VALIDATION",
    "audit_market_data": "EXECUTION_LIFECYCLE",
    "download_market_data": "EXECUTION_LIFECYCLE",
}


def chatgpt_tools() -> list[dict[str, object]]:
    """Advertise no autonomous Codex start/stop and no broker/order operations."""
    canonical = [dict(item) for item in _tools() if item["name"] in _CHATGPT_CANONICAL]
    # Only GPT-facing read-only status tools advertise an optional full response.
    for item in canonical:
        if item["name"] == "get_dashboard_status":
            item["inputSchema"] = {
                "type": "object",
                "properties": {
                    "response_mode": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "Full can be very large; summary is context-budgeted.",
                    },
                },
                "additionalProperties": False,
            }
    custom: list[dict[str, object]] = [
        {
            "name": "get_research_brief",
            "description": "Read sanitized research context, Frontier and prior failure evidence.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "response_mode": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "run_research_step",
            "description": (
                "Execute one external GPT-authored ResearchIntent against canonical Strategy IR; "
                "strict mutation validation and immutable Evidence, never place orders."
            ),
            "inputSchema": _chat_directed_step_schema(),
        },
    ]
    step_schema = _chat_directed_step_schema()
    step_properties = step_schema["properties"]
    if not isinstance(step_properties, dict):
        raise TypeError("research step tool properties are invalid")
    guided_submit_schema = {
        **step_schema,
        "properties": {
            "session_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
            "checkpoint_token": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
            "generation": {"type": "integer", "minimum": 1, "maximum": MAX_GENERATIONS},
            "source_path": {"type": "string"},
            "intent": step_properties["intent"],
        },
        "required": ["session_id", "checkpoint_token", "generation", "source_path", "intent"],
    }
    custom.extend(
        [
            {
                "name": "start_guided_research",
                "description": "Create externally GPT-directed session with pinned policy gates.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "data_path": {"type": "string"},
                        "generations": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_GENERATIONS,
                        },
                        "method": {"type": "string", "enum": ["grid", "random", "bayesian"]},
                        "count": {"type": "integer", "minimum": 1, "maximum": MAX_CANDIDATES},
                        "seed": {"type": "integer", "minimum": 0},
                        "min_trades": {"type": "integer", "minimum": 30},
                        "min_annual_trades": {"type": "integer", "minimum": 30},
                        "min_qqq_cagr_delta": {"type": "number", "minimum": 0.1},
                    },
                    "required": ["data_path", "generations"],
                },
            },
            {
                "name": "get_guided_research",
                "description": "Read immutable Evidence-based GPT checkpoint; never auto-advance.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"session_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"}},
                    "required": ["session_id"],
                },
            },
            {
                "name": "reconcile_guided_research",
                "description": "Reconcile guided Evidence without re-evaluating.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"session_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"}},
                    "required": ["session_id"],
                },
            },
            {
                "name": "submit_guided_generation",
                "description": "Execute one GPT-directed, uniquely authorized research generation.",
                "inputSchema": guided_submit_schema,
            },
        ]
    )
    step_properties = step_schema["properties"]
    if not isinstance(step_properties, dict):
        raise TypeError("research step tool properties are invalid")
    batch_schema = {
        **step_schema,
        "properties": {
            **{
                key: value
                for key, value in step_properties.items()
                if key != "previous_research_run_id"
            },
            "generations": {"type": "integer", "minimum": 1, "maximum": MAX_GENERATIONS},
            "count": {"type": "integer", "minimum": 1, "maximum": MAX_CANDIDATES},
            "parameter_domains": {
                "type": "array",
                "maxItems": 4,
                "description": (
                    "Optional GPT-authored bounded search spaces. Different values "
                    "produce distinct candidate strategies even if no prior candidate survives."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "values": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 24,
                            "items": {
                                "anyOf": [
                                    {"type": "integer"},
                                    {"type": "number"},
                                    {"type": "string"},
                                    {"type": "boolean"},
                                ]
                            },
                        },
                    },
                    "required": ["name", "values"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["source_path", "data_path", "intent", "generations"],
    }
    status_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"job_id": {"type": "string", "description": "Omit for most recent batch"}},
        "additionalProperties": False,
    }
    custom.extend(
        [
            {
                "name": "preflight_research_batch",
                "description": (
                    "Read-only validation of strategy and Parquet data with a bounded "
                    "preview of duplicate or unique candidate strategies. Never launches a worker."
                ),
                "inputSchema": batch_schema,
            },
            {
                "name": "start_research_batch",
                "description": "Execute a bounded 1-100 generation GPT-planned research batch. "
                "No local LLM calls; returns job ID, status and measured ETA.",
                "inputSchema": batch_schema,
            },
            {
                "name": "get_research_batch_status",
                "description": "Check batch completion, progress and historically measured ETA.",
                "inputSchema": status_schema,
            },
            {
                "name": "get_research_batch_report",
                "description": "Report generation times, verified successor IDs and funnel counts. "
                "Final report only after completion; no OOS approval implied.",
                "inputSchema": {
                    **status_schema,
                    "properties": {
                        **status_schema["properties"],
                        "response_mode": {
                            "type": "string",
                            "enum": ["summary", "full"],
                            "default": "summary",
                        },
                    },
                },
            },
            {
                "name": "resume_research_batch",
                "description": "Resume matching interrupted batch checkpoints only.",
                "inputSchema": status_schema,
            },
            {
                "name": "cancel_research_batch",
                "description": "Stop after current generation; retain completed Evidence.",
                "inputSchema": status_schema,
            },
        ]
    )
    custom.extend(
        [
            {
                "name": "list_market_data",
                "description": (
                    "List exact local immutable market-data paths and whether read-only "
                    "Tiingo/KIS sources are configured. No credentials or rows exposed."
                ),
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "audit_market_data",
                "description": (
                    "Audit development-only market snapshot hashes, PIT limitations, "
                    "optional independent vendor raw prices and adjusted/raw factors. "
                    "pin_snapshot registers an immutable local reproducibility fingerprint "
                    "but never independently certifies historical PIT."
                ),
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "data_path": {"type": "string"},
                        "comparison_path": {"type": "string"},
                        "adjusted_path": {"type": "string"},
                        "pin_snapshot": {"type": "boolean", "default": False},
                    },
                    "required": ["data_path"],
                },
            },
            {
                "name": "validate_market_data",
                "description": (
                    "Inspect existing managed Parquet OHLCV, declared lineage and quality."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"data_path": {"type": "string"}},
                    "required": ["data_path"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "download_market_data",
                "description": (
                    "Explicitly fetch US equity/ETF daily prices from configured read-only "
                    "Tiingo or KIS, verify date coverage, and save immutable development "
                    "Parquet. No account orders, API keys, or arbitrary URLs accepted."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "provider": {"type": "string", "enum": ["tiingo", "kis"]},
                        "symbol": {"type": "string", "minLength": 1, "maxLength": 15},
                        "start": {"type": "string", "format": "date"},
                        "end": {"type": "string", "format": "date"},
                        "price_policy": {
                            "type": "string",
                            "enum": ["raw", "total_return_adjusted"],
                            "default": "raw",
                        },
                    },
                    "required": ["provider", "symbol", "start", "end"],
                    "additionalProperties": False,
                },
            },
        ]
    )
    session_field = {"type": "string", "pattern": "^[0-9a-f]{32}$"}
    token_field = {"type": "string", "pattern": "^[0-9a-f]{32}$"}

    def _academic_tool(
        name: str,
        description: str,
        properties: dict[str, object],
        required: list[str],
    ) -> dict[str, object]:
        return {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        }

    custom.extend(
        [
            _academic_tool(
                "start_algorithm_research",
                "Start a bounded development-only algorithm research session. "
                "Returns a typed AlgorithmPlan prompt via the existing MCP URL.",
                {
                    "data_path": {"type": "string"},
                    "generations": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                ["data_path", "generations"],
            ),
            _academic_tool(
                "get_algorithm_research",
                "Read verified research history and current GPT planning or diagnostic checkpoint.",
                {"session_id": session_field},
                ["session_id"],
            ),
            _academic_tool(
                "submit_algorithm_plan",
                "Validate a GPT AlgorithmPlan, or a bounded ResearchIntent when "
                "the model context identifies a replay-verified inherited parent. "
                "Optional require_execution_change compares the inherited child's canonical "
                "costed fills to the selected parent BEFORE staging or counting a generation, "
                "and rejects identical behavior while preserving the plan checkpoint token. "
                "A retry of the latest acknowledged checkpoint returns its prior stage.",
                {
                    "session_id": session_field,
                    "checkpoint_token": token_field,
                    "plan": {"type": "object"},
                    "require_execution_change": {"type": "boolean", "default": False},
                },
                ["session_id", "checkpoint_token", "plan"],
            ),
            _academic_tool(
                "submit_algorithm_diagnosis",
                "Validate GPT diagnosis and commit one researched generation. Optional "
                "require_signal_change rejects proven redundant regime-filter ablations "
                "before consuming a checkpoint. Latest identical retries return the previously "
                "committed generation without running experiments again.",
                {
                    "session_id": session_field,
                    "checkpoint_token": token_field,
                    "diagnosis": {"type": "object"},
                    "require_signal_change": {"type": "boolean", "default": False},
                },
                ["session_id", "checkpoint_token", "diagnosis"],
            ),
            _academic_tool(
                "resume_algorithm_research",
                "Explicitly resume a failed checkpoint; preserves all completed generations.",
                {"session_id": session_field},
                ["session_id"],
            ),
            _academic_tool(
                "cancel_algorithm_research",
                "Cancel academic research at its current checkpoint, keeping completed Evidence.",
                {"session_id": session_field, "checkpoint_token": token_field},
                ["session_id", "checkpoint_token"],
            ),
            _academic_tool(
                "reconcile_algorithm_research",
                "Operator-only recovery after the previous worker has fully stopped. "
                "Restores missing S7 evidence before planning continues; repeated "
                "recovery is read-only while the checkpoint remains unchanged.",
                {"session_id": session_field},
                ["session_id"],
            ),
            _academic_tool(
                "evaluate_algorithm_experiments",
                "Evaluate saved GPT hypotheses with unchanged DEVELOPMENT control; "
                "optionally replay a hash-verified S7 child and test a continuation "
                "mutation at the existing checkpoint, never place orders.",
                {
                    "session_id": session_field,
                    "generation": {"type": "integer", "minimum": 1, "maximum": 100},
                    "checkpoint_token": token_field,
                    "hypothesis_id": {"type": "string", "minLength": 3, "maxLength": 96},
                    "child_strategy_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "continuation_intent": {"type": "object"},
                },
                ["session_id", "generation"],
            ),
        ]
    )
    return canonical + custom


class _OAuthTool(types.Tool):
    """Published per-tool OAuth security declaration for OpenAI clients."""

    security_schemes: list[dict[str, object]] = Field(alias="securitySchemes")


class _OAuthToolsResult(types.ListToolsResult):
    @field_serializer("tools")
    def serialize_tools(self, tools: list[types.Tool]) -> list[dict[str, object]]:
        # SDK's list[Tool] annotation otherwise strips subclass securitySchemes.
        return [tool.model_dump(by_alias=True, exclude_none=True) for tool in tools]


class ChatGPTMCPAdapter(SDKMCPServerAdapter):
    """Distinct official SDK tool plane with no local-LLM autonomous actions."""

    def __init__(
        self,
        *,
        state_dir: Path,
        project_root: Path,
        require_oauth: bool = False,
        audit: MCPAuditLog | None = None,
    ) -> None:
        super().__init__(state_dir=state_dir, project_root=project_root)
        self.require_oauth = require_oauth
        self.audit = audit
        # Validate at the external ChatGPT boundary, before any tool-specific
        # dispatcher can create state, start research or fetch market data.
        self._input_validators: dict[str, Draft202012Validator] = {}
        for item in chatgpt_tools():
            schema = item["inputSchema"]
            if not isinstance(schema, dict) or not isinstance(item["name"], str):
                raise TypeError("invalid advertised MCP tool contract")
            Draft202012Validator.check_schema(schema)
            self._input_validators[item["name"]] = Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            )
        if len(self._input_validators) != 32:
            raise TypeError("unexpected ChatGPT tool contract count")

    async def list_tools(
        self,
        _context: ServerRequestContext[Any],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        tools = [_sdk_tool(item) for item in chatgpt_tools()]
        if self.audit is not None:
            self.audit.emit("tools_list", result="OK", count=len(tools))
        if not self.require_oauth:
            return types.ListToolsResult(tools=tools)
        return _OAuthToolsResult(
            tools=[
                _OAuthTool.model_validate(
                    {
                        **item.model_dump(by_alias=True, exclude_none=True),
                        "securitySchemes": [{"type": "oauth2", "scopes": ["mcp:tools"]}],
                    }
                )
                for item in tools
            ]
        )

    async def call_tool(
        self,
        _context: ServerRequestContext[Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        if params.name not in (_CHATGPT_CANONICAL | _CHATGPT_CUSTOM.keys()):
            if self.audit is not None:
                self.audit.emit(
                    "tool_call", tool="unknown", result="ERROR", error_code="UNKNOWN_TOOL"
                )
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"}, is_error=True
            )
        arguments = params.arguments
        try:
            if not isinstance(arguments, dict):
                raise ValueError("MCP arguments must be an object")
            # Defensive bounded JSON parsing; do not echo potentially sensitive
            # or adversarial content back into error results or audit logs.
            serialized = json.dumps(arguments, ensure_ascii=False, allow_nan=False)
            if len(serialized.encode("utf-8")) > 256 * 1024:
                raise ValueError("MCP input exceeds bounded limit")
            self._input_validators[params.name].validate(arguments)
        except (ValueError, TypeError, JSONSchemaValidationError):
            if self.audit is not None:
                self.audit.emit(
                    "tool_call",
                    tool=params.name,
                    result="ERROR",
                    error_code="INVALID_TOOL_ARGUMENTS",
                )
            return _sdk_tool_result(
                {
                    "status": "ERROR",
                    "error_code": "INVALID_TOOL_ARGUMENTS",
                    "message": "tool input does not match the published contract",
                    "orders_enabled": False,
                },
                is_error=True,
            )
        response_mode = str(arguments.get("response_mode", "summary"))
        dispatch_arguments = (
            {key: value for key, value in arguments.items() if key != "response_mode"}
            if params.name in COMPACTABLE_TOOLS
            else arguments
        )
        result = await super().call_tool(
            _context,
            types.CallToolRequestParams(name=params.name, arguments=dispatch_arguments),
        )
        if self.audit is not None:
            error_code = None
            if (
                result.is_error
                and result.content
                and isinstance(result.content[0], types.TextContent)
            ):
                try:
                    error_code = json.loads(result.content[0].text).get("error_code")
                except (ValueError, AttributeError):
                    pass
            self.audit.emit(
                "tool_call",
                tool=params.name,
                result="ERROR" if result.is_error else "OK",
                error_code=error_code or ("TOOL_EXECUTION_FAILED" if result.is_error else None),
            )
        if result.is_error or (
            params.name not in _CHATGPT_CUSTOM and params.name not in COMPACTABLE_TOOLS
        ):
            return result
        content = result.content[0]
        if not isinstance(content, types.TextContent):
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"}, is_error=True
            )
        payload = json.loads(content.text)
        if not isinstance(payload, dict):
            return _sdk_tool_result(
                {"status": "ERROR", "message": "tool request failed"}, is_error=True
            )
        if params.name in _CHATGPT_CUSTOM:
            payload["_contract"] = PublicToolContractMetadata(
                tool=params.name, plane=_CHATGPT_CUSTOM[params.name], orders_enabled=False
            ).model_dump(mode="json")
        if params.name in COMPACTABLE_TOOLS:
            original_bytes = encoded_size(payload)
            payload = compact_mcp_context(params.name, payload, response_mode=response_mode)
            append_context_metrics(
                self.state_dir,
                tool=params.name,
                original_bytes=original_bytes,
                returned_bytes=encoded_size(payload),
                mode=response_mode,
            )
        return _sdk_tool_result(payload, is_error=False)


def create_chatgpt_sdk_adapter(
    *,
    state_dir: Path,
    project_root: Path,
    require_oauth: bool = False,
    audit: MCPAuditLog | None = None,
) -> ChatGPTMCPAdapter:
    return ChatGPTMCPAdapter(
        state_dir=state_dir,
        project_root=project_root,
        require_oauth=require_oauth,
        audit=audit,
    )
