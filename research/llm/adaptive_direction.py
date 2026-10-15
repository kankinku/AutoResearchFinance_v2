"""S8 research-budget guidance derived from audited generations and paired trials.

This is ADVISORY ONLY: the external authenticated LLM remains responsible for
strategy hypotheses and chooses its next mode. Development performance is not
proof of generalization, and no synthetic utility score is called expected alpha.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from core.integrity.hashes import content_hash

Mode = Literal["EXPLORE", "TEST_HYPOTHESIS", "EVOLVE"]
_ALLOWED_STATES = frozenset({
    "NO_OBSERVED_EFFECT", "DIRECTION_MATCHED_DEVELOPMENT_ONLY",
    "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY", "METRIC_UNAVAILABLE",
    "DEGENERATE_INACTIVE_CHILD",
})


class ResearchBudgetError(ValueError):
    """Unreliable generation or experimental evidence."""


def build_research_direction(
    history: Sequence[Mapping[str, Any]],
    controlled_reports: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    """Recommend the next research mode without executing or selecting alpha.

    Only audited, already-persisted Evidence should be supplied. A generation
    is counted once, not once per proposal/backtest. Counts are descriptive,
    not fixed model quotas or a claim of adaptive policy superiority.
    """
    if len(history) > 100 or len(controlled_reports) > len(history):
        raise ResearchBudgetError("unbounded or inconsistent generation evidence")
    known: set[str] = set()
    duplicated = 0
    for i, item in enumerate(history, 1):
        if (type(item.get("generation")) is not int or item["generation"] != i
                or not isinstance(item.get("evidence_hash"), str)
                or len(item["evidence_hash"]) != 64):
            raise ResearchBudgetError("invalid generation order or evidence identity")
        semantic = item.get("algorithm_semantic_hash")
        if not isinstance(semantic, str) or len(semantic) != 64:
            raise ResearchBudgetError("missing semantic strategy identity")
        if semantic in known:
            duplicated += 1
        known.add(semantic)
    if any(type(generation) is not int or generation < 1 or generation > len(history)
           for generation in controlled_reports):
        raise ResearchBudgetError("experiment has no corresponding completed generation")
    states: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    by_generation: dict[int, tuple[dict[str, Any], ...]] = {}
    tested = 0
    comparisons = 0
    for generation in sorted(controlled_reports):
        row = controlled_reports[generation]
        if row.get("original_generation_evidence_hash") != history[generation - 1]["evidence_hash"]:
            raise ResearchBudgetError("control is not bound to original generation")
        report = row.get("report")
        if not isinstance(report, dict) or report.get("causal_status") != "NOT_ESTABLISHED":
            raise ResearchBudgetError("unverified controlled experiment report")
        experiments = report.get("experiments")
        if not isinstance(experiments, (list, tuple)) or len(experiments) > 5:
            raise ResearchBudgetError("unexpected hypothesis comparison count")
        recent: list[dict[str, Any]] = []
        for observation in experiments:
            if not isinstance(observation, dict):
                raise ResearchBudgetError("unstructured experiment outcome")
            state = observation.get("status")
            if (state not in _ALLOWED_STATES
                    or observation.get("causal_status") != "NOT_ESTABLISHED"):
                raise ResearchBudgetError("unsupported or promoted experiment status")
            # Old immutable reports can have the pre-fix positive direction
            # label for a zero-trade child. Do NOT change their hashed evidence;
            # normalize ONLY the advisory reading of the old observation.
            parent_fills = observation.get("parent_fill_count")
            child_fills = observation.get("child_fill_count")
            if (parent_fills is not None or child_fills is not None) and (
                type(parent_fills) is not int or type(child_fills) is not int
                or parent_fills < 0 or child_fills < 0
            ):
                raise ResearchBudgetError("invalid experiment fill counts")
            if (parent_fills is not None and parent_fills > 0
                    and child_fills == 0):
                state = "DEGENERATE_INACTIVE_CHILD"
            delta = observation.get("execution_delta")
            if not isinstance(delta, dict):
                raise ResearchBudgetError("missing measured execution attribution")
            if any(type(delta.get(key)) is not int or delta[key] < 0 for key in (
                "added_event_count", "removed_event_count", "resized_event_count"
            )):
                raise ResearchBudgetError("invalid measured execution counts")
            if delta["added_event_count"] or delta["removed_event_count"]:
                kind = "SIGNAL_TIMING_CHANGED"
            elif delta["resized_event_count"]:
                kind = "SIZE_ONLY_CHANGED"
            else:
                kind = "UNCHANGED_EXECUTIONS"
            kinds[kind] += 1
            states[state] += 1
            tested += 1
            recent.append({
                "hypothesis_id": observation.get("hypothesis_id"),
                "observed_result": state,
                "execution_change": kind,
            })
        if report.get("multiple_comparison_notice"):
            comparisons += 1
        by_generation[generation] = tuple(recent)
    latest = len(history)
    last_trials = by_generation.get(latest)
    latest_proposals = history[-1].get("hypothesis_ids", []) if history else []
    if not history:
        selected: Mode = "EXPLORE"
        basis = "NO_COMPLETED_GENERATIONS"
    elif last_trials is None and latest_proposals:
        selected = "TEST_HYPOTHESIS"
        basis = "LATEST_GENERATION_HAS_UNTESTED_HYPOTHESES"
    elif last_trials:
        novel_matching = any(
            item["observed_result"] == "DIRECTION_MATCHED_DEVELOPMENT_ONLY"
            and item["execution_change"] == "SIGNAL_TIMING_CHANGED"
            for item in last_trials
        )
        if novel_matching and not controlled_reports[latest]["report"].get(
            "multiple_comparison_notice"
        ):
            selected = "EVOLVE"
            basis = "LAST_CONTROL_MEASURED_NONTRIVIAL_SIGNAL_CHANGE"
        elif all(
            item["observed_result"] == "DEGENERATE_INACTIVE_CHILD"
            for item in last_trials
        ):
            selected = "EXPLORE"
            basis = "LAST_CONTROL_INACTIVE_CHILD"
        elif all(item["observed_result"] == "NO_OBSERVED_EFFECT" for item in last_trials):
            selected = "EXPLORE"
            basis = "LAST_CONTROL_NO_OBSERVED_EFFECT"
        elif all(item["observed_result"] == "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY"
                 for item in last_trials):
            selected = "EXPLORE"
            basis = "LAST_CONTROL_DIRECTION_REJECTED"
        else:
            selected = "TEST_HYPOTHESIS"
            basis = "RESULTS_REQUIRE_CONFOUNDING_CHECKS"
    else:
        selected = "EXPLORE"
        basis = "NO_ACTIONABLE_CAUSAL_EVIDENCE"
    # Historical results may show a failure to find novel rules; do not
    # reward repeated strategies or double-count hypotheses as generations.
    if duplicated >= 2:
        selected = "EXPLORE"
        basis = "REPEATED_SEMANTIC_STRATEGIES"
    evidence = {
        "generation_hashes": [x["evidence_hash"] for x in history],
        "controlled_record_hashes": [controlled_reports[g].get("record_hash")
                                     for g in sorted(controlled_reports)],
        "completed_generations": len(history),
    }
    return {
        "schema": "adaptive-research-direction-v1",
        "status": "RESEARCH_BUDGET_GUIDANCE_ONLY",
        "recommended_mode": selected,
        "reason_code": basis,
        "allowed_modes": ["EXPLORE", "EVOLVE", "TEST_HYPOTHESIS"],
        "llm_may_override": True,
        "allocation_is_not_fixed_quota": True,
        "completed_generations": latest,
        "unique_strategy_count": len(known),
        "repeated_strategy_count": duplicated,
        "experiment_outcome_count": tested,
        "experiment_status_counts": dict(sorted(states.items())),
        "execution_change_counts": dict(sorted(kinds.items())),
        "multiple_comparison_generations": comparisons,
        "last_generation_observations": list(last_trials or ())[:5],
        "causal_status": "NOT_ESTABLISHED",
        "independent_oos_approved": False,
        "real_trading_enabled": False,
        "evidence_hash": content_hash(evidence),
    }
