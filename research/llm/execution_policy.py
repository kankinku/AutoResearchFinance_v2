"""Project-wide research orchestration preference, independent from broker mode.

ChatGPT uses the existing authenticated Quant MCP endpoint by default.
External paid model APIs are optional and require explicit operator opt-in.
"""
from __future__ import annotations

from typing import Literal

ResearchExecutionMode = Literal["mcp", "openai-api"]
DEFAULT_RESEARCH_EXECUTION_MODE: ResearchExecutionMode = "mcp"


def research_execution_policy() -> dict[str, object]:
    """Return a fresh, read-only-advertised description of the effective default."""
    return {
        "default_mode": DEFAULT_RESEARCH_EXECUTION_MODE,
        "default_controller": "authenticated_chatgpt_mcp_client",
        "default_requires_openai_api_key": False,
        "mcp_existing_registration_required": True,
        "model_api_mode": "openai-api",
        "model_api_explicit_opt_in_required": True,
        "model_api_auto_enabled": False,
        "orders_enabled": False,
        "mcp_research_tools": [
            "get_research_brief", "start_algorithm_research",
            "get_algorithm_research", "submit_algorithm_plan",
            "submit_algorithm_diagnosis", "evaluate_algorithm_experiments",
            "resume_algorithm_research", "cancel_algorithm_research",
            "reconcile_algorithm_research",
        ],
        "model_api_notes": (
            "Only an explicit operator CLI --execution-mode openai-api with --model "
            "and OPENAI_API_KEY can call a separate metered model API. "
            "Never infer permission from the presence of an environment key."
        ),
    }
