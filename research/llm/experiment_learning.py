"""D05: evidence-bound research failure memory, not causal attribution or alpha approval.

Derived deterministically from immutable S7 controlled development reports. The
external ChatGPT MCP researcher remains the only proposal author; we supply
bounded disconfirmation, avoid-repeat fingerprints and next-test suggestions.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from core.integrity.hashes import content_hash


class ExperimentLearningError(ValueError):
    """Reject forged, mismatched or unsupported past experiments."""


_STATES = frozenset({
    "NO_OBSERVED_EFFECT", "DIRECTION_MATCHED_DEVELOPMENT_ONLY",
    "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY", "METRIC_UNAVAILABLE",
    "DEGENERATE_INACTIVE_CHILD",
})

# Interpret measured results, never assert their hypothetical mechanism is true.
_NEXT: dict[str, tuple[str, str]] = {
    "NO_OBSERVED_EFFECT": ("UNCHANGED_OBSERVED_TRACE", "RULE_STRUCTURE"),
    "DIRECTION_MATCHED_DEVELOPMENT_ONLY": ("UNREPLICATED_DEVELOPMENT_MATCH", "ABLATION"),
    "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY": ("PREDICTION_CONTRADICTED", "PARAMETER"),
    "METRIC_UNAVAILABLE": ("MISSING_OBSERVABLE_METRIC", "PARAMETER"),
    "DEGENERATE_INACTIVE_CHILD": ("NO_ACTIVE_CHILD_TRADES", "ABLATION"),
}


def build_experiment_learning(
    history: Sequence[Mapping[str, Any]],
    records: Mapping[int, Mapping[str, Any]],
    *,
    max_recent: int = 12,
) -> dict[str, Any]:
    """Generate bounded cross-generation feedback from committed S7 evidence only.

    Experiments are descriptive developer-data comparisons, not trained model
    parameters, independent counterfactual controls or a broker-ready decision.
    No LLM or backtest is invoked and no source evidence is modified.
    """
    if not 1 <= max_recent <= 50 or len(history) > 300 or len(records) > len(history):
        raise ExperimentLearningError("unbounded experiment learning request")
    for k, past_generation in enumerate(history, 1):
        if (
            type(past_generation.get("generation")) is not int
            or past_generation["generation"] != k
            or not isinstance(past_generation.get("evidence_hash"), str)
            or len(past_generation["evidence_hash"]) != 64
        ):
            raise ExperimentLearningError("untrusted generation history order")
    results: list[dict[str, Any]] = []
    seen_child_hashes: set[str] = set()
    counts: Counter[str] = Counter()
    for generation in sorted(records):
        if type(generation) is not int or generation < 1 or generation > len(history):
            raise ExperimentLearningError("orphan experiment generation")
        body = records[generation]
        report_hash = body.get("record_hash")
        if not isinstance(report_hash, str) or len(report_hash) != 64:
            raise ExperimentLearningError("missing immutable S7 report hash")
        original = {key: value for key, value in body.items() if key != "record_hash"}
        if content_hash(original) != report_hash:
            raise ExperimentLearningError("controlled report integrity mismatch")
        ancestor = history[generation - 1]
        if (
            body.get("generation") != generation
            or body.get("original_generation_evidence_hash") != ancestor["evidence_hash"]
            or body.get("study_scope") != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
        ):
            raise ExperimentLearningError("controlled report not bound to ancestor")
        report = body.get("report")
        if not isinstance(report, dict) or (
            report.get("causal_status") != "NOT_ESTABLISHED"
            or report.get("out_of_sample_approved") is not False
            or report.get("broker_executable") is not False
            or report.get("diagnostic_proposal_hash")
            != ancestor.get("diagnostic_proposal_hash")
        ):
            raise ExperimentLearningError("controlled experiment cannot support learned claims")
        proposals = ancestor.get("experiments")
        observed = report.get("experiments")
        if (
            not isinstance(proposals, list)
            or not isinstance(observed, (list, tuple))
            or len(proposals) != len(observed)
            or len(observed) > 5
        ):
            raise ExperimentLearningError("original hypothesis count mismatch")
        offered = {item["hypothesis_id"]: item for item in proposals}
        if len(offered) != len(proposals):
            raise ExperimentLearningError("duplicate original hypotheses")
        completed: set[str] = set()
        for item in observed:
            if not isinstance(item, dict):
                raise ExperimentLearningError("unstructured comparison")
            hid = item.get("hypothesis_id")
            if not isinstance(hid, str) or hid not in offered or hid in completed:
                raise ExperimentLearningError("mismatched experiment identity")
            completed.add(hid)
            proposal = offered[hid]
            status = item.get("status")
            if (
                status not in _STATES
                or item.get("causal_status") != "NOT_ESTABLISHED"
                or item.get("child_strategy_hash") != proposal.get("proposal_child_hash")
                or item.get("expected_direction") != proposal.get("predicted_direction")
                or item.get("metric") != proposal.get("expected_metric")
            ):
                raise ExperimentLearningError("experiment provenance or status mismatch")
            delta = item.get("delta")
            if delta is not None and (
                type(delta) not in (float, int) or not math.isfinite(delta)
            ):
                raise ExperimentLearningError("nonfinite metric delta")
            execution = item.get("execution_delta")
            if not isinstance(execution, dict) or any(
                type(execution.get(key)) is not int or execution[key] < 0
                for key in ("added_event_count", "removed_event_count", "resized_event_count")
            ):
                raise ExperimentLearningError("missing measured execution differences")
            before, after = item.get("parent_fill_count"), item.get("child_fill_count")
            if (not isinstance(before, int) or isinstance(before, bool)
                    or not isinstance(after, int) or isinstance(after, bool)
                    or before < 0 or after < 0):
                raise ExperimentLearningError("invalid fill count")
            # Legacy immutable S7 could have labelled a zero-fill improvement.
            if before > 0 and after == 0:
                status = "DEGENERATE_INACTIVE_CHILD"
            reason, suggested_design = _NEXT[status]
            if (
                status == "DIRECTION_MATCHED_DEVELOPMENT_ONLY"
                and report.get("multiple_comparison_notice")
            ):
                reason = "MULTIPLE_COMPARISONS_NO_ALPHA_EVIDENCE"
                suggested_design = "ABLATION"
            child_hash = item["child_strategy_hash"]
            duplicate = child_hash in seen_child_hashes
            seen_child_hashes.add(child_hash)
            counts[reason] += 1
            changes = {
                "added": execution["added_event_count"],
                "removed": execution["removed_event_count"],
                "resized": execution["resized_event_count"],
            }
            results.append({
                "generation": generation,
                "hypothesis_id": hid,
                "original_observed_ids": proposal.get("observed_ids", []),
                "hypothesized_mechanism": proposal.get("mechanism"),
                "alternative_explanation": proposal.get("alternative"),
                "original_test_design": proposal.get("test_design"),
                "parent_evidence_hash": ancestor["evidence_hash"],
                "controlled_record_hash": report_hash,
                "child_strategy_hash": child_hash,
                "status": status,
                "finding_code": reason,
                "metric": item["metric"],
                "observed_delta": delta,
                "execution_changes": changes,
                "same_fill_trace": item.get("same_fill_trace") is True,
                "repeated_child_strategy": duplicate,
                "original_hypothesis_not_verified": True,
                "suggested_test_design": suggested_design,
            })
    recent = results[-max_recent:]
    avoid = list(dict.fromkeys(
        event["child_strategy_hash"] for event in results
        if event["finding_code"] in {
            "UNCHANGED_OBSERVED_TRACE", "PREDICTION_CONTRADICTED",
            "NO_ACTIVE_CHILD_TRADES",
        }
    ))[-20:]
    latest_generation = len(history)
    actionable = [item for item in recent if item["generation"] == latest_generation]
    if any(event["finding_code"] == "NO_ACTIVE_CHILD_TRADES" for event in actionable):
        priority = "RESTORE_ACTIVITY_AND_CONTRAST_UNCHANGED_PARENT"
    elif any(event["finding_code"] == "PREDICTION_CONTRADICTED" for event in actionable):
        priority = "TEST_COUNTERHYPOTHESIS_WITH_SINGLE_CHANGE"
    elif any(event["finding_code"] == "MULTIPLE_COMPARISONS_NO_ALPHA_EVIDENCE"
             for event in actionable):
        priority = "ABLATE_ONE_RULE_AND_ACCOUNT_FOR_MULTIPLE_TRIALS"
    elif any(event["finding_code"] == "UNREPLICATED_DEVELOPMENT_MATCH"
             for event in actionable):
        priority = "ABLATE_ONE_RULE_BEFORE_ANY_EVOLUTION"
    elif any(event["finding_code"] == "UNCHANGED_OBSERVED_TRACE"
             for event in actionable):
        priority = "EXPLORE_NEW_CAUSAL_MECHANISM"
    elif history:
        priority = "RECONCILE_MISSING_MEASUREMENTS_OR_EXPLORE"
    else:
        priority = "EXPLORE_UNTESTED_HYPOTHESIS"
    return {
        "schema": "evidence-bound-experiment-learning-v1",
        "status": "LLM_FOLLOWUP_GUIDANCE_ONLY",
        "generation_count": latest_generation,
        "measured_experiment_count": len(results),
        "unmeasured_generation_count": len(history) - len(records),
        "failure_and_uncertainty_counts": dict(sorted(counts.items())),
        "recent_evidence": recent,
        "avoid_retesting_identical_child_hashes": avoid,
        "next_test_priority": priority,
        "evidence_hash": content_hash({
            "generation_hashes": [gen["evidence_hash"] for gen in history],
            "s7_hashes": [records[g]["record_hash"] for g in sorted(records)],
        }),
        "llm_may_author_next_typed_plan": True,
        "automatic_strategy_execution": False,
        "causal_status": "NOT_ESTABLISHED",
        "independent_oos_approved": False,
        "broker_executable": False,
    }
