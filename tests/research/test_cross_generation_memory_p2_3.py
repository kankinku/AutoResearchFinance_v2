"""P2-3: typed repeat detection and paired economic disconfirmation."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from core.integrity.hashes import content_hash
from research.llm.cross_generation_memory import (
    CrossGenerationMemoryError,
    build_cross_generation_memory,
    intervention_identity,
)
from tests.research.test_experiment_learning_d05 import _example


def _case(
    generation: int,
    *,
    cutoff: float = 0.55,
    child_diff: float = -100.0,
    parent_strategy: str = "e" * 64,
    child_hash: str | None = None,
    operation: str = "REPLACE_RULE",
) -> tuple[dict, dict]:
    child_hash = child_hash or (f"{generation:064x}")
    history, reports = _example(
        generation=generation,
        evidence=f"{generation + 10:064x}",
        child_hash=child_hash,
        status="DIRECTION_MATCHED_DEVELOPMENT_ONLY",
    )
    ancestor = history[0]
    ancestor.update(
        {
            "strategy_hash": parent_strategy,
            "measured_final_equity": 15000.0,
            "metrics": {"total_return": 0.5, "max_drawdown": 0.09, "exposure": 0.30},
        }
    )
    ancestor["experiments"][0]["proposed_intent"] = {
        "mode": "structure",
        "parent_ids": [f"parent-{generation}"],
        "rationale": f"LLM wording of explanation {generation}",
        "operations": [
            {
                "op": operation,
                "path": "exit.conditions.0",
                "condition": {
                    "left": "plan_vote_score",
                    "op": "less_equal",
                    "value": cutoff,
                    "enabled": True,
                },
            }
        ],
    }
    row = reports[generation]
    trial = row["report"]["experiments"][0]
    trial.update(
        {
            "parent_final_equity": 15000.0,
            "child_final_equity": 15000.0 + child_diff,
            "execution_delta": {
                **trial["execution_delta"],
                "parent_costs": 120.0,
                "child_costs": 119.0,
            },
            "development_windows": [
                {"parent_max_drawdown": 0.08, "child_max_drawdown": 0.09} for _ in range(4)
            ],
        }
    )
    row["report"].update(
        {
            "dataset_hash": "same-development-data",
            "audit_hash": "a" * 64,
        }
    )
    raw = {k: v for k, v in row.items() if k != "record_hash"}
    return ancestor, {**raw, "record_hash": content_hash(raw)}


def test_typed_intervention_fingerprint_ignores_llm_narrative_but_not_parameter() -> None:
    first, _ = _case(1, cutoff=0.35)
    second, _ = _case(2, cutoff=0.55)
    a = intervention_identity(first["experiments"][0], parent_strategy_hash="a" * 64)
    b = intervention_identity(second["experiments"][0], parent_strategy_hash="b" * 64)
    assert a is not None and b is not None
    assert a["family_fingerprint"] == b["family_fingerprint"]
    assert a["exact_fingerprint"] != b["exact_fingerprint"]
    replica = deepcopy(second["experiments"][0])
    replica["proposed_intent"]["operations"][0]["condition"]["value"] = 0.35
    assert intervention_identity(replica)["exact_fingerprint"] == a["exact_fingerprint"]
    removal = {
        "proposed_intent": {
            "mode": "structure",
            "operations": [{"op": "REMOVE_RULE", "path": "entry.conditions.2"}],
        }
    }
    assert (
        intervention_identity(removal, parent_strategy_hash="a" * 64)["family_fingerprint"]
        != intervention_identity(removal, parent_strategy_hash="b" * 64)["family_fingerprint"]
    )
    assert intervention_identity({"proposed_intent": {"operations": []}}) is None


def test_repeated_negative_family_and_exact_repeat_are_detected_without_alpha_claims() -> None:
    h1, r1 = _case(1, cutoff=0.35, child_diff=-100)
    h2, r2 = _case(2, cutoff=0.5, child_diff=-50, parent_strategy=h1["strategy_hash"])
    h3, r3 = _case(3, cutoff=0.35, child_diff=-120, parent_strategy=h1["strategy_hash"])
    memory = build_cross_generation_memory([h1, h2, h3], {1: r1, 2: r2, 3: r3})
    assert memory == build_cross_generation_memory([h1, h2, h3], {1: r1, 2: r2, 3: r3})
    assert memory["counted_s7_trials"] == 3
    assert memory["distinct_intervention_families"] == 1
    assert memory["repeated_exact_parent_intervention_count"] == 1
    assert memory["duplicate_child_strategy_hash_count"] == 0
    family = memory["frequent_intervention_families"][0]
    assert family["return_worse"] == 3
    assert family["economic_guidance"] == "REVIEW_REPEATED_NET_LOSSES_BEFORE_SIMILAR_TEST"
    assert memory["repeated_failure_families"]
    assert memory["recent_verified_results"][-1]["repeated_exact_intervention_on_same_parent"]
    assert memory["automatic_strategy_execution"] is False
    assert memory["independent_oos_approved"] is False
    assert memory["causal_status"] == "NOT_ESTABLISHED"
    assert memory["development_mdd_windows_are_not_full_period_mdd"] is True


def test_mixed_better_majority_not_misclassified_as_repeated_failure() -> None:
    history, reports = [], {}
    for i, equity_delta in enumerate((120.0, 180.0, 200.0, -20.0), 1):
        h, r = _case(i, cutoff=0.35 + i * 0.01, child_diff=equity_delta)
        history.append(h)
        reports[i] = r
    memory = build_cross_generation_memory(history, reports)
    assert not memory["repeated_failure_families"]
    family = memory["frequent_intervention_families"][0]
    assert family["return_better"] == 3
    assert family["return_worse"] == 1
    assert family["economic_guidance"] == "MOSTLY_BETTER_BUT_CONTRADICTORY_DEVELOPMENT_RESULTS"


def test_wrong_parent_equity_or_cost_fails_even_if_report_is_resealed() -> None:
    h, r = _case(1)
    forged = deepcopy(r)
    forged["report"]["experiments"][0]["parent_final_equity"] = 14000.0
    body = {k: v for k, v in forged.items() if k != "record_hash"}
    with pytest.raises((CrossGenerationMemoryError, ValueError), match="parent"):
        build_cross_generation_memory([h], {1: {**body, "record_hash": content_hash(body)}})
    forged2 = deepcopy(r)
    forged2["report"]["experiments"][0]["execution_delta"]["child_costs"] = -1
    body2 = {k: v for k, v in forged2.items() if k != "record_hash"}
    with pytest.raises((CrossGenerationMemoryError, ValueError), match="cost"):
        build_cross_generation_memory([h], {1: {**body2, "record_hash": content_hash(body2)}})
    forged3 = deepcopy(r)
    forged3["report"]["causal_status"] = "ESTABLISHED"
    body3 = {k: v for k, v in forged3.items() if k != "record_hash"}
    with pytest.raises(ValueError, match="support|unverified|causal"):
        build_cross_generation_memory([h], {1: {**body3, "record_hash": content_hash(body3)}})


def test_no_generation_memory_and_unmeasured_are_explicit() -> None:
    empty = build_cross_generation_memory([], {})
    assert empty["counted_s7_trials"] == 0
    assert empty["completed_generations"] == 0
    h1, r1 = _case(1)
    h2, _ = _case(2)
    value = build_cross_generation_memory([h1, h2], {1: r1})
    assert value["unmeasured_generations"] == 1
    assert value["counted_s7_trials"] == 1


def test_mcp_next_plan_exposes_memory_without_advancing_session(tmp_path: Path) -> None:
    from tests.integrations.test_academic_mcp_sessions import _setup
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    server, started = _setup(tmp_path)
    assert started["model_context"]["cross_generation_memory"]["counted_s7_trials"] == 0
    model = ScriptedResearcher()
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": model.propose(started["model_context"]),
        },
    )
    result = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": model.propose(staged["model_context"]),
        },
    )
    memory = result["model_context"]["cross_generation_memory"]
    assert memory["completed_generations"] == 1
    assert memory["counted_s7_trials"] >= 1
    assert (
        memory["source_learning_evidence_hash"]
        == result["model_context"]["experiment_learning"]["evidence_hash"]
    )
    assert (
        result["history"][0]["diagnostic_context_hash"] == staged["model_context"]["context_hash"]
    )
    fetched = server._dispatch("get_algorithm_research", {"session_id": started["session_id"]})
    assert fetched["model_context"]["cross_generation_memory"] == memory
    assert fetched["completed_generations"] == 1
    assert fetched["orders_enabled"] is False
