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
    assert a["measured_outcome_metrics"]["direction_match_rate"] is None
    assert a["measured_outcome_metrics"]["repeated_failure_rate"] is None
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


def test_learning_measures_execution_change_repeat_failures_and_direction_match() -> None:
    history, records = [], {}
    for generation, (state, hash_value, effect) in enumerate((
        ("NO_OBSERVED_EFFECT", "c" * 64, 0),
        ("NO_OBSERVED_EFFECT", "c" * 64, 0),
        ("DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY", "d" * 64, 1),
        ("DIRECTION_MATCHED_DEVELOPMENT_ONLY", "e" * 64, 1),
    ), 1):
        h, row = _example(
            generation=generation, evidence=f"{generation:064x}",
            status=state, child_hash=hash_value,
        )
        trial = row[generation]["report"]["experiments"][0]
        trial["execution_delta"]["added_event_count"] = effect
        row[generation] = _repair(row[generation])
        history.extend(h)
        records.update(row)

    learning = build_experiment_learning(history, records)
    counters = learning["measured_outcome_metrics"]
    assert counters["measured_trials"] == 4
    assert counters["execution_change_trials"] == 2
    assert counters["same_fill_or_no_execution_change_trials"] == 2
    assert counters["repeated_failure_trials"] == 1
    assert counters["failure_trials"] == 3
    assert counters["repeated_failure_rate"] == pytest.approx(1 / 3)
    assert counters["direction_comparable_trials"] == 2
    assert counters["direction_matched_trials"] == 1
    assert counters["direction_match_rate"] == 0.5
    assert counters["unobserved_hypotheses_not_counted"] is True
    assert learning["automatic_strategy_execution"] is False
    assert learning["independent_oos_approved"] is False


def test_learning_rejects_same_fill_trace_claiming_new_executed_signals() -> None:
    h, records = _example(status="DIRECTION_MATCHED_DEVELOPMENT_ONLY")
    trial = records[1]["report"]["experiments"][0]
    trial["same_fill_trace"] = True
    trial["execution_delta"]["added_event_count"] = 1
    records[1] = _repair(records[1])
    feedback = build_experiment_learning(h, records)
    assert feedback["recent_evidence"][0]["same_fill_trace_despite_decision_changes"]
    assert feedback["recent_evidence"][0]["finding_code"] == (
        "UNCHANGED_FILLS_DESPITE_REPORTED_DECISION_CHANGES"
    )
    assert feedback["measured_outcome_metrics"]["execution_change_trials"] == 0
    assert feedback["next_test_priority"] != "ABLATE_ONE_RULE_BEFORE_ANY_EVOLUTION"


def test_older_failures_still_contribute_when_recent_context_is_truncated() -> None:
    history, records = [], {}
    for generation in range(1, 16):
        h, report = _example(
            generation=generation,
            evidence=f"{generation:064x}",
            child_hash=f"{generation:064x}",
            status=(
                "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY"
                if generation == 1 else "NO_OBSERVED_EFFECT"
            ),
        )
        history.extend(h)
        records.update(report)
    learning = build_experiment_learning(history, records, max_recent=5)
    assert len(learning["recent_evidence"]) == 5
    assert learning["recent_evidence"][0]["generation"] == 11
    assert learning["measured_outcome_metrics"]["measured_trials"] == 15
    assert learning["measured_outcome_metrics"]["failure_trials"] == 15
    assert learning["failure_and_uncertainty_counts"]["PREDICTION_CONTRADICTED"] == 1


def test_same_fill_matched_metric_without_decision_change_is_not_new_signal() -> None:
    history, reports = _example(status="DIRECTION_MATCHED_DEVELOPMENT_ONLY")
    reports[1]["report"]["experiments"][0]["same_fill_trace"] = True
    reports[1] = _repair(reports[1])
    memory = build_experiment_learning(history, reports)
    assert memory["recent_evidence"][0]["finding_code"] == "UNCHANGED_OBSERVED_TRACE"
    assert memory["measured_outcome_metrics"]["execution_change_trials"] == 0
    assert memory["next_test_priority"] == "EXPLORE_NEW_CAUSAL_MECHANISM"
