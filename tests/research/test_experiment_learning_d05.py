"""D05 evidence-bound learning tests: provenance, repetition, counterfactual humility."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from core.integrity.hashes import content_hash
from research.llm.experiment_learning import ExperimentLearningError, build_experiment_learning
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _example(
    *,
    status: str = "NO_OBSERVED_EFFECT",
    fills: tuple[int, int] = (2, 2),
    multi: bool = False,
    child_hash: str = "c" * 64,
    evidence: str = "b" * 64,
    generation: int = 1,
) -> tuple[list[dict], dict[int, dict]]:
    proposal = {
        "hypothesis_id": "hyp_1",
        "proposal_child_hash": child_hash,
        "observed_ids": ["obs-17"],
        "mechanism": "Entry rule may suppress trades in adverse regimes.",
        "alternative": "Missed trades may reflect long lookback rather than market regime.",
        "test_design": "ABLATION",
        "predicted_direction": "INCREASE",
        "expected_metric": "total_return",
    }
    history = [{
        "generation": generation,
        "evidence_hash": evidence,
        "diagnostic_proposal_hash": "d" * 64,
        "algorithm_semantic_hash": "a" * 64,
        "experiments": [proposal],
    }]
    measured = {
        "hypothesis_id": "hyp_1",
        "child_strategy_hash": child_hash,
        "status": status,
        "causal_status": "NOT_ESTABLISHED",
        "metric": "total_return",
        "expected_direction": "INCREASE",
        "delta": 0.2,
        "parent_fill_count": fills[0],
        "child_fill_count": fills[1],
        "same_fill_trace": status == "NO_OBSERVED_EFFECT",
        "execution_delta": {
            "added_event_count": 0, "removed_event_count": 0,
            "resized_event_count": 0,
        },
    }
    body = {
        "generation": generation,
        "original_generation_evidence_hash": evidence,
        "study_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        "report": {
            "causal_status": "NOT_ESTABLISHED",
            "out_of_sample_approved": False,
            "broker_executable": False,
            "multiple_comparison_notice": multi,
            "diagnostic_proposal_hash": "d" * 64,
            "experiments": [measured],
        },
    }
    return history, {generation: {**body, "record_hash": content_hash(body)}}


def _repair(report: dict) -> dict:
    body = {k: v for k, v in report.items() if k != "record_hash"}
    return {**body, "record_hash": content_hash(body)}


def test_no_evidence_is_bounded_exploration() -> None:
    a = build_experiment_learning([], {})
    assert a["next_test_priority"] == "EXPLORE_UNTESTED_HYPOTHESIS"
    assert a["measured_experiment_count"] == 0
    assert a["automatic_strategy_execution"] is False
    assert a["independent_oos_approved"] is False
    assert a == build_experiment_learning([], {})


@pytest.mark.parametrize(("state", "expected_reason", "priority"), [
    ("NO_OBSERVED_EFFECT", "UNCHANGED_OBSERVED_TRACE", "EXPLORE_NEW_CAUSAL_MECHANISM"),
    ("DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY", "PREDICTION_CONTRADICTED",
     "TEST_COUNTERHYPOTHESIS_WITH_SINGLE_CHANGE"),
    ("DEGENERATE_INACTIVE_CHILD", "NO_ACTIVE_CHILD_TRADES",
     "RESTORE_ACTIVITY_AND_CONTRAST_UNCHANGED_PARENT"),
    ("METRIC_UNAVAILABLE", "MISSING_OBSERVABLE_METRIC",
     "RECONCILE_MISSING_MEASUREMENTS_OR_EXPLORE"),
    ("DIRECTION_MATCHED_DEVELOPMENT_ONLY", "UNREPLICATED_DEVELOPMENT_MATCH",
     "ABLATE_ONE_RULE_BEFORE_ANY_EVOLUTION"),
])
def test_failure_types_generate_disconfirming_next_tests(
    state: str, expected_reason: str, priority: str,
) -> None:
    history, evidence = _example(status=state)
    response = build_experiment_learning(history, evidence)
    assert response["next_test_priority"] == priority
    item = response["recent_evidence"][0]
    assert item["finding_code"] == expected_reason
    assert item["parent_evidence_hash"] == history[0]["evidence_hash"]
    assert item["controlled_record_hash"] == evidence[1]["record_hash"]
    assert item["original_observed_ids"] == ["obs-17"]
    assert "suppress trades" in item["hypothesized_mechanism"]
    assert "long lookback" in item["alternative_explanation"]
    assert item["original_test_design"] == "ABLATION"
    assert item["original_hypothesis_not_verified"] is True
    assert response["causal_status"] == "NOT_ESTABLISHED"


def test_zero_fill_and_multiple_comparisons_cannot_claim_success() -> None:
    h, r = _example(status="DIRECTION_MATCHED_DEVELOPMENT_ONLY", fills=(5, 0))
    memory = build_experiment_learning(h, r)
    assert memory["recent_evidence"][0]["finding_code"] == "NO_ACTIVE_CHILD_TRADES"
    assert memory["next_test_priority"].startswith("RESTORE_ACTIVITY")

    h, r = _example(status="DIRECTION_MATCHED_DEVELOPMENT_ONLY", multi=True)
    memory = build_experiment_learning(h, r)
    assert memory["recent_evidence"][0]["finding_code"] == "MULTIPLE_COMPARISONS_NO_ALPHA_EVIDENCE"
    assert memory["next_test_priority"] == "ABLATE_ONE_RULE_AND_ACCOUNT_FOR_MULTIPLE_TRIALS"
    assert memory["broker_executable"] is False


def test_repeated_child_experiment_warns_even_when_generation_changes() -> None:
    first, reports = _example()
    second, two = _example(generation=2, evidence="e" * 64)
    merged = build_experiment_learning(first + second, {**reports, **two})
    assert merged["measured_experiment_count"] == 2
    assert merged["recent_evidence"][1]["repeated_child_strategy"] is True
    assert len(merged["avoid_retesting_identical_child_hashes"]) == 1
    assert merged["generation_count"] == 2


def test_missing_measurement_not_invented_as_failure() -> None:
    first, reports = _example()
    second, _ = _example(generation=2, evidence="f" * 64)
    result = build_experiment_learning(first + second, reports)
    assert result["measured_experiment_count"] == 1
    assert result["unmeasured_generation_count"] == 1
    assert result["next_test_priority"] == "RECONCILE_MISSING_MEASUREMENTS_OR_EXPLORE"


@pytest.mark.parametrize(("path", "value", "message"), [
    (("original_generation_evidence_hash",), "0" * 64, "integrity|bound|mismatch"),
    (("report", "causal_status"), "ESTABLISHED", "integrity|unverified|support"),
    (("report", "out_of_sample_approved"), True, "integrity|unverified|support"),
    (("report", "experiments", 0, "hypothesis_id"), "forged", "integrity|mismatch"),
    (("report", "experiments", 0, "child_strategy_hash"), "0" * 64,
     "integrity|provenance"),
    (("report", "experiments", 0, "delta"), "NaN", "integrity|nonfinite"),
])
def test_tampered_and_inconsistent_result_fails_closed(path, value, message) -> None:
    history, records = _example()
    modified = deepcopy(records[1])
    item = modified
    for key in path[:-1]:
        item = item[key]
    item[path[-1]] = value
    if path == ("original_generation_evidence_hash",):
        records[1] = _repair(modified)
        with pytest.raises(ExperimentLearningError, match="bound"):
            build_experiment_learning(history, records)
    else:
        records[1] = _repair(modified)
        with pytest.raises(ExperimentLearningError, match=message):
            build_experiment_learning(history, records)


def test_hash_only_tampering_is_caught() -> None:
    history, reports = _example()
    reports[1]["record_hash"] = "0" * 64
    with pytest.raises(ExperimentLearningError, match="integrity"):
        build_experiment_learning(history, reports)


def test_live_mcp_two_generation_context_exposes_evidence_bound_memory(tmp_path: Path) -> None:
    server, initial = _setup(tmp_path)
    provider = ScriptedResearcher()
    start_context = initial["model_context"]
    assert start_context["experiment_learning"]["measured_experiment_count"] == 0
    staged = server._dispatch("submit_algorithm_plan", {
        "session_id": initial["session_id"],
        "checkpoint_token": initial["checkpoint_token"],
        "plan": provider.propose(start_context),
    })
    finished = server._dispatch("submit_algorithm_diagnosis", {
        "session_id": initial["session_id"],
        "checkpoint_token": staged["checkpoint_token"],
        "diagnosis": provider.propose(staged["model_context"]),
    })
    memory = finished["model_context"]["experiment_learning"]
    assert memory["measured_experiment_count"] >= 1
    assert memory["generation_count"] == 1
    assert memory["recent_evidence"][0]["parent_evidence_hash"] == finished["history"][0][
        "evidence_hash"
    ]
    assert all(x["causal_status"] == "NOT_ESTABLISHED" for x in [
        finished["model_context"]["research_direction"], memory,
    ])
    assert memory == server._dispatch("get_algorithm_research", {
        "session_id": initial["session_id"],
    })["model_context"]["experiment_learning"]
    restarted = server._dispatch("submit_algorithm_plan", {
        "session_id": initial["session_id"],
        "checkpoint_token": finished["checkpoint_token"],
        "plan": provider.propose(finished["model_context"]),
    })
    result = server._dispatch("submit_algorithm_diagnosis", {
        "session_id": initial["session_id"],
        "checkpoint_token": restarted["checkpoint_token"],
        "diagnosis": provider.propose(restarted["model_context"]),
    })
    assert result["status"] == "COMPLETED"
    assert result["history"][0]["evidence_hash"] == finished["history"][0]["evidence_hash"]
    assert result["orders_enabled"] is False
