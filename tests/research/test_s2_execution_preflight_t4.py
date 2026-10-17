"""T4 S2: hash-different inherited candidates must change canonical fills."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent
from research.llm.s2_execution_preflight import (
    UnchangedCanonicalExecution,
    compare_inherited_s2_execution,
)
from tests.research.test_lineage_p0_3 import SID
from tests.research.test_p0_3b_inherited_audit import _real
from tests.research.test_p0_3b_reinherit import _isolated_service


def _mutate_exit(parent, value: float):
    intent = ResearchIntent.model_validate(
        {
            "mode": "structure",
            "parent_ids": [parent.strategy.strategy_id],
            "operations": [
                {
                    "op": "REPLACE_RULE",
                    "path": "exit.conditions.0",
                    "condition": {
                        "left": parent.strategy.exit.conditions[0].left,
                        "op": "less_equal",
                        "value": value,
                    },
                }
            ],
            "rationale": "S2 preflight regression threshold sweep",
        }
    )
    ir = apply_intent(parent.strategy, intent, research_feature_specs())
    h = content_hash(ir.model_dump(mode="json", by_alias=True))
    return intent, replace(parent, strategy=ir, strategy_hash=h)


def test_same_canonical_fills_even_when_ir_hash_changes_are_rejected() -> None:
    market, parent = _real()
    _, candidate = _mutate_exit(parent, parent.strategy.exit.conditions[0].value + 0.00000001)
    assert candidate.strategy_hash != parent.strategy_hash
    measured = audit_inherited_decisions(candidate, market)
    assert measured.evaluation.trades == audit_inherited_decisions(parent, market).evaluation.trades
    with pytest.raises(UnchangedCanonicalExecution, match="UNCHANGED_CANONICAL_FILLS"):
        compare_inherited_s2_execution(parent, measured, market)


def test_distinct_fills_yield_hash_bound_bounded_preflight() -> None:
    market, parent = _real()
    _, candidate = _mutate_exit(parent, 0.9)
    measured = audit_inherited_decisions(candidate, market)
    receipt = compare_inherited_s2_execution(parent, measured, market)
    assert receipt["status"] == "VERIFIED_DIFFERENT_COSTED_FILLS"
    assert receipt["candidate_strategy_hash"] == candidate.strategy_hash
    assert receipt["parent_strategy_hash"] == parent.strategy_hash
    assert receipt["parent_canonical_fills_hash"] != receipt["candidate_canonical_fills_hash"]
    assert receipt["comparison_is_development_only"]
    assert receipt["broker_executable"] is False
    assert receipt["independent_oos_approved"] is False


def test_actual_checkpoint_rejects_same_fills_without_consuming_token(tmp_path: Path) -> None:
    svc = _isolated_service(tmp_path)
    initial = svc.get({"session_id": SID})
    assert initial["completed_generations"] == 33
    assert initial["checkpoint_phase"] == "AWAITING_PLAN"
    c = initial["model_context"]
    assert c["output_contract"] == "InheritedResearchIntent"
    exit_cond = c["inherited_parent_exit_conditions"][0]
    parent_id = c["inherited_parent_strategy_id"]
    plan = {
        "mode": "structure",
        "parent_ids": [parent_id],
        "operations": [
            {
                "op": "REPLACE_RULE",
                "path": "exit.conditions.0",
                "condition": {**exit_cond, "value": exit_cond["value"] + 1e-8},
            }
        ],
        "rationale": "Historical no-execution-change candidate; must reject unchanged fills",
    }
    with pytest.raises(ValueError, match="UNCHANGED_CANONICAL_FILLS"):
        svc.submit_plan(
            {
                "session_id": SID,
                "checkpoint_token": initial["checkpoint_token"],
                "plan": plan,
                "require_execution_change": True,
            }
        )
    after = svc.get({"session_id": SID})
    assert after["checkpoint_token"] == initial["checkpoint_token"]
    assert after["checkpoint_phase"] == "AWAITING_PLAN"
    assert after["completed_generations"] == 33
    assert after["history"] == initial["history"]
    with pytest.raises(ValueError, match="boolean"):
        svc.submit_plan(
            {
                "session_id": SID,
                "checkpoint_token": initial["checkpoint_token"],
                "plan": plan,
                "require_execution_change": 1,
            }
        )
    amended = {
        **plan,
        "operations": [{**plan["operations"][0], "condition": {**exit_cond, "value": 0.9}}],
    }
    staged = svc.submit_plan(
        {
            "session_id": SID,
            "checkpoint_token": initial["checkpoint_token"],
            "plan": amended,
            "require_execution_change": True,
        }
    )
    assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    assert staged["completed_generations"] == 33
    metadata = staged["model_context"]["s2_execution_preflight"]
    assert metadata["status"] == "VERIFIED_DIFFERENT_COSTED_FILLS"
    assert metadata == svc.get({"session_id": SID})["model_context"]["s2_execution_preflight"]
    assert metadata["same_fill_trace"] is False
    assert staged["model_context"]["context_hash"]
    assert (
        svc.submit_plan(
            {
                "session_id": SID,
                "checkpoint_token": initial["checkpoint_token"],
                "plan": amended,
                "require_execution_change": True,
            }
        )
        == staged
    )
    with pytest.raises(ValueError, match="replay|checkpoint|different|conflict"):
        svc.submit_plan(
            {
                "session_id": SID,
                "checkpoint_token": initial["checkpoint_token"],
                "plan": amended,
                "require_execution_change": False,
            }
        )


def test_additive_tool_schema_exposes_optional_s2_guard_without_url_change() -> None:
    tools = {t["name"]: t for t in chatgpt_tools()}
    assert len(tools) == 32
    schema = tools["submit_algorithm_plan"]["inputSchema"]
    assert schema["properties"]["require_execution_change"] == {"type": "boolean", "default": False}
    assert "require_execution_change" not in schema["required"]
    assert "public_url" not in schema["properties"]
