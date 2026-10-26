"""Cross-fork preservation checks for a direct GPT <-> Quant MCP runtime.

No provider invocation, OAuth change, sealed OOS or order operation is performed.
"""

from __future__ import annotations

from inspect import signature
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.features.registry import research_feature_specs
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from integrations.python_mcp_direct import PUBLIC_READ_TOOLS
from research.indicator_engine.seed import ACADEMIC_SIGNALS
from research.llm import (
    adaptive_direction,
    composite_crossover_v3,
    cross_generation_memory,
    experiment_learning,
    feature_contribution_f3,
    feature_evidence_profile,
    lineage_selection,
    model_provenance_v1,
    parent_portfolio_v2,
    regime_portfolio_v3,
    regime_router_v3,
    weakness_feature_matcher,
)

REQUIRED_MCP_RESEARCH_TOOLS = frozenset(
    {
        "start_algorithm_research",
        "get_algorithm_research",
        "submit_algorithm_plan",
        "submit_algorithm_diagnosis",
        "evaluate_algorithm_experiments",
        "resume_algorithm_research",
        "reconcile_algorithm_research",
        "cancel_algorithm_research",
    }
)


def test_direct_gpt_quant_mcp_generation_tools_preserved() -> None:
    tools = chatgpt_tools()
    assert len(tools) == 32
    names = {tool["name"] for tool in tools}
    assert len(names) == 32
    assert REQUIRED_MCP_RESEARCH_TOOLS <= names
    submit_plan = next(tool for tool in tools if tool["name"] == "submit_algorithm_plan")
    assert "require_trade_activity" in str(submit_plan)


def test_173_feature_library_and_separate_academic_validation_scope() -> None:
    catalog = research_feature_specs()
    assert len(catalog) >= 173
    names = {item.name for item in catalog}
    assert {"rsi", "macd", "parkinson", "atr", "hurst", "kalman_slope"} <= names
    assert "sma_direction" in {signal.signal_id for signal in ACADEMIC_SIGNALS}
    assert len(ACADEMIC_SIGNALS) < len(catalog)


def test_existing_academic_service_research_gates_remain_opt_in() -> None:
    params = signature(AcademicMCPCheckpointService).parameters
    for option in (
        "parent_portfolio_v2",
        "generalization_parent_v1",
        "p4_quality_gate_v1",
        "p4_s7_quality_v1",
    ):
        assert option in params
        assert params[option].default is False
    assert "p4_model_capture_v1" in params
    # The server contract passes preflight switches inside a typed args dictionary.
    assert "args" in signature(AcademicMCPCheckpointService.submit_plan).parameters


def test_optional_python_sdk_is_not_automatic_model_decision_host() -> None:
    assert PUBLIC_READ_TOOLS == frozenset(
        {
            "get_workspace_status",
            "list_features",
            "get_algorithm_research",
        }
    )
    assert callable(adaptive_direction.build_research_direction)
    assert callable(cross_generation_memory.build_cross_generation_memory)
    assert callable(experiment_learning.build_experiment_learning)
    assert callable(parent_portfolio_v2.verified_parent_lanes)
    assert callable(lineage_selection.choose_development_parent)
    assert callable(feature_evidence_profile.build_verified_catalog_feature_profiles)
    assert callable(weakness_feature_matcher.build_weakness_feature_guidance)
    assert callable(feature_contribution_f3.build_costed_s7_contribution)
    assert callable(composite_crossover_v3.compose)
    assert callable(regime_router_v3.resolve_regime_routes)
    assert callable(regime_portfolio_v3.simulate_regime_portfolio)
    assert hasattr(model_provenance_v1, "verify_capture")


def test_scope_contract_file_is_unchanged() -> None:
    import hashlib

    source = (
        Path(__file__).resolve().parents[2]
        / "docs/decisions/2026-10-14-autoresearch-interview-20q.md"
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (
        "ab41bbb68bf410ae9914c628d38915678472d5a906ee75e2cf2dae9ad8bfb801"
    )
