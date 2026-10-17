"""P2-3: deterministic, evidence-linked cross-generation research memory.

Observed net outcomes and rule intervention signatures are intentionally NOT
market insight, causal verification, independent replicates, or alpha training.
Only immutable and fully checked S7 reports may enter the memory. The GPT MCP
planning layer receives bounded advice; no promotion or order is performed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from math import isclose, isfinite
from typing import Any

from core.integrity.hashes import content_hash
from research.llm.economic_feedback import build_economic_feedback
from research.llm.experiment_learning import build_experiment_learning


class CrossGenerationMemoryError(ValueError):
    """An ungrounded experiment must never become cross-generation evidence."""


def intervention_identity(
    proposal: Mapping[str, Any], *, parent_strategy_hash: str | None = None
) -> dict[str, Any] | None:
    """Separate *exact* typed change from an indicator/intervention family.

    Ignore freeform rationale, proposed IDs and LLM wording. The family is
    useful for searching similar changes but does not mean identical behavior.
    A missing or untyped operation has no fingerprint; never group unknowns.
    """
    intent = proposal.get("proposed_intent")
    if not isinstance(intent, Mapping):
        return None
    operations = intent.get("operations")
    if not isinstance(operations, list) or not 1 <= len(operations) <= 8:
        return None
    exact: list[dict[str, Any]] = []
    family: list[dict[str, Any]] = []
    for raw in operations:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("op"), str):
            return None
        op = raw["op"]
        if op == "RETAIN":
            return None
        path = raw.get("path")
        if path is not None and not isinstance(path, str):
            return None
        target = raw.get("condition")
        feature = raw.get("feature")
        indicator = raw.get("indicator")
        normalized: dict[str, Any] = {"op": op, "path": path}
        target_family: dict[str, Any] = {"op": op, "path": path}
        # A removal by array index alone does not identify its indicator/rule
        # across different parent StrategyIR layouts. Treat such families as
        # parent-specific rather than falsely pooling unrelated interventions.
        if op in {"REMOVE_RULE", "REMOVE_REGIME_FILTER", "ENABLE_RULE", "DISABLE_RULE"}:
            target_family["unresolved_target_parent_hash"] = parent_strategy_hash
        if isinstance(target, Mapping):
            normalized["condition"] = dict(target)
            target_family.update({"signal": target.get("left"), "operator": target.get("op")})
        if isinstance(feature, Mapping):
            normalized["feature"] = dict(feature)
            target_family["feature"] = feature.get("name", feature.get("feature_id"))
        if isinstance(indicator, Mapping):
            normalized["indicator"] = dict(indicator)
            target_family["indicator"] = indicator.get("name", indicator.get("indicator_id"))
        for key in ("value", "logic"):
            if raw.get(key) is not None:
                normalized[key] = raw[key]
                if key == "logic":
                    target_family[key] = raw[key]
        exact.append(normalized)
        family.append(target_family)
    # Ordered operations are important when two changes target one index.
    exact_hash = content_hash({"mode": intent.get("mode"), "operations": exact})
    family_hash = content_hash({"mode": intent.get("mode"), "operation_families": family})
    return {
        "exact_fingerprint": exact_hash,
        "family_fingerprint": family_hash,
        "operation_family": family,
        "operation_count": len(operations),
        "same_family_does_not_imply_same_strategy": True,
    }


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not isfinite(value):
        raise CrossGenerationMemoryError(f"invalid costed {label}")
    return float(value)


def build_cross_generation_memory(
    history: Sequence[Mapping[str, Any]],
    records: Mapping[int, Mapping[str, Any]],
    *,
    max_families: int = 12,
    max_recent: int = 8,
) -> dict[str, Any]:
    """Aggregate net child-parent comparisons with mandatory evidence integrity.

    The exact child hash and typed intervention are kept separate. If the
    parent strategy changed, even the *same* operation is not an identical
    experimental control. Retesting may be justified; this is an advisory.
    """
    if type(max_families) is not int or not 1 <= max_families <= 20:
        raise CrossGenerationMemoryError("invalid bounded family budget")
    if type(max_recent) is not int or not 1 <= max_recent <= 20:
        raise CrossGenerationMemoryError("invalid bounded recent budget")
    # Existing fail-closed validators cover checkpoint continuity, immutable
    # report hashes, reported metric identities, child fill counts, 4 windows,
    # and parent final equity before we derive any new memory.
    validated_learning = build_experiment_learning(history, records)
    validated_economics = build_economic_feedback(history, records)
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_items: list[dict[str, Any]] = []
    child_keys: set[str] = set()
    exact_parent_keys: set[tuple[str, str]] = set()
    same_children = 0
    same_parent_interventions = 0
    unknown_intents = 0
    for generation, row in sorted(records.items()):
        source = history[generation - 1]
        proposals = {p["hypothesis_id"]: p for p in source["experiments"]}
        report = row["report"]
        for trial in report["experiments"]:
            proposal = proposals[trial["hypothesis_id"]]
            parent = _finite(trial.get("parent_final_equity"), "parent final equity")
            child = _finite(trial.get("child_final_equity"), "child final equity")
            if (
                parent <= 0
                or child < 0
                or not isclose(
                    parent,
                    _finite(source.get("measured_final_equity"), "generation equity"),
                    rel_tol=1e-7,
                    abs_tol=0.0001,
                )
            ):
                raise CrossGenerationMemoryError("S7 actual costed parent identity mismatch")
            costs = trial.get("execution_delta")
            if not isinstance(costs, Mapping):
                raise CrossGenerationMemoryError("missing executed S7 cost attribution")
            parent_cost = _finite(costs.get("parent_costs"), "parent transaction costs")
            child_cost = _finite(costs.get("child_costs"), "child transaction costs")
            if parent_cost < 0 or child_cost < 0:
                raise CrossGenerationMemoryError("negative transaction cost")
            parent_strategy_hash = source.get("strategy_hash")
            if not isinstance(parent_strategy_hash, str) or len(parent_strategy_hash) != 64:
                raise CrossGenerationMemoryError("missing parent strategy identity")
            fingerprint = intervention_identity(proposal, parent_strategy_hash=parent_strategy_hash)
            if fingerprint is None:
                unknown_intents += 1
            child_hash = trial["child_strategy_hash"]
            same_child = child_hash in child_keys
            child_keys.add(child_hash)
            same_children += int(same_child)
            exact_parent_key = (
                parent_strategy_hash,
                fingerprint["exact_fingerprint"] if fingerprint else "UNCLASSIFIED",
            )
            exact_parent_repeat = fingerprint is not None and exact_parent_key in exact_parent_keys
            if fingerprint is not None:
                exact_parent_keys.add(exact_parent_key)
            same_parent_interventions += int(exact_parent_repeat)
            delta = child - parent
            if trial.get("parent_fill_count", 0) > 0 and trial.get("child_fill_count", 0) == 0:
                outcome = "INACTIVE_CHILD"
            elif isclose(delta, 0, rel_tol=1e-12, abs_tol=1e-7):
                outcome = "NO_NET_GAIN"
            elif delta > 0:
                outcome = "RETURN_BETTER"
            else:
                outcome = "RETURN_WORSE"
            windows = trial["development_windows"]
            worse_windows = sum(
                1
                for win in windows
                if _finite(win.get("child_max_drawdown"), "window MDD")
                > _finite(win.get("parent_max_drawdown"), "parent window MDD") + 1e-9
            )
            finding = {
                "generation": generation,
                "hypothesis_id": proposal["hypothesis_id"],
                "original_mechanism_claim": proposal.get("mechanism"),
                "alternative_explanation": proposal.get("alternative"),
                "original_observed_ids": proposal.get("observed_ids"),
                "parent_strategy_hash": parent_strategy_hash,
                "child_strategy_hash": child_hash,
                "exact_fingerprint": fingerprint["exact_fingerprint"] if fingerprint else None,
                "family_fingerprint": fingerprint["family_fingerprint"] if fingerprint else None,
                "operation_family": fingerprint["operation_family"] if fingerprint else None,
                "observed_metric": trial.get("metric"),
                "direction_match": trial.get("status"),
                "outcome": outcome,
                "net_equity_delta": round(delta, 8),
                "paid_cost_delta": round(child_cost - parent_cost, 8),
                "worsened_retrospective_mdd_windows": worse_windows,
                "full_period_child_mdd_verified": False,
                "repeated_child_hash": same_child,
                "repeated_exact_intervention_on_same_parent": exact_parent_repeat,
                "original_generation_evidence_hash": source["evidence_hash"],
                "original_s7_record_hash": row["record_hash"],
                "causal_status": "NOT_ESTABLISHED",
            }
            all_items.append(finding)
            if fingerprint:
                by_family[fingerprint["family_fingerprint"]].append(finding)
    summaries: list[dict[str, Any]] = []
    for family_hash, events in by_family.items():
        c = Counter(e["outcome"] for e in events)
        unique_children = len({e["child_strategy_hash"] for e in events})
        independent_parents = len({e["parent_strategy_hash"] for e in events})
        repeats = sum(e["repeated_exact_intervention_on_same_parent"] for e in events)
        worse_windows = sum(e["worsened_retrospective_mdd_windows"] for e in events)
        # Multiple parameter values under the same operation family are
        # exploratory variations, never independent confirmations.
        bad = c["RETURN_WORSE"] + c["INACTIVE_CHILD"]
        good = c["RETURN_BETTER"]
        if bad >= 2 and bad > good:
            guidance = "REVIEW_REPEATED_NET_LOSSES_BEFORE_SIMILAR_TEST"
        elif bad >= 2 and bad == good:
            guidance = "MIXED_ECONOMIC_RESULTS_REQUIRE_COMPETING_HYPOTHESES"
        elif good >= 2 and bad:
            guidance = "MOSTLY_BETTER_BUT_CONTRADICTORY_DEVELOPMENT_RESULTS"
        elif good >= 2:
            guidance = "REPEATED_DEVELOPMENT_GAINS_REQUIRE_ABLATION_AND_OOS"
        elif repeats:
            guidance = "EXACT_PARENT_INTERVENTION_ALREADY_TESTED"
        else:
            guidance = "INSUFFICIENT_CROSS_GENERATION_EVIDENCE"
        summaries.append(
            {
                "family_fingerprint": family_hash,
                "operation_family": events[0]["operation_family"],
                "measured_trials": len(events),
                "distinct_child_strategy_hashes": unique_children,
                "distinct_parent_strategy_hashes": independent_parents,
                "repeated_same_parent_intervention": repeats,
                "return_better": c["RETURN_BETTER"],
                "return_worse": c["RETURN_WORSE"],
                "return_unchanged": c["NO_NET_GAIN"],
                "inactive_child": c["INACTIVE_CHILD"],
                "retrospective_mdd_windows_worse_total": worse_windows,
                "economic_guidance": guidance,
                "latest_source_generation": events[-1]["generation"],
                "observed_mdd_is_full_period": False,
                "independent_replicates": False,
            }
        )
    summaries.sort(key=lambda x: (-x["measured_trials"], x["family_fingerprint"]))
    latest = all_items[-max_recent:]
    pending = [
        x
        for x in summaries
        if x["economic_guidance"] == "REVIEW_REPEATED_NET_LOSSES_BEFORE_SIMILAR_TEST"
    ]
    avoid = [
        {
            "parent_strategy_hash": e["parent_strategy_hash"],
            "exact_fingerprint": e["exact_fingerprint"],
            "generation": e["generation"],
        }
        for e in all_items
        if e["exact_fingerprint"] is not None
    ][-30:]
    proof = {
        "generation_evidence_hashes": [p["evidence_hash"] for p in history],
        "S7_record_hashes": [records[g]["record_hash"] for g in sorted(records)],
        "typed_family_descriptors": sorted(by_family),
    }
    return {
        "schema": "p2-3-cross-generation-evidence-memory-v1",
        "status": "ADVISORY_ONLY_VERIFIED_S7_DEVELOPMENT",
        "completed_generations": len(history),
        "counted_s7_trials": len(all_items),
        "unmeasured_generations": len(history) - len(records),
        "distinct_intervention_families": len(summaries),
        "unclassified_historical_intents": unknown_intents,
        "duplicate_child_strategy_hash_count": same_children,
        "repeated_exact_parent_intervention_count": same_parent_interventions,
        "observed_outcome_counts": dict(sorted(Counter(x["outcome"] for x in all_items).items())),
        "frequent_intervention_families": summaries[:max_families],
        "repeated_failure_families": pending[:max_families],
        "recent_verified_results": latest,
        "exact_prior_parent_interventions": avoid,
        "next_plan_guidance": (
            "Do not re-test the same typed intervention on the same parent without a "
            "specific new control or market regime; examine repeated adverse families "
            "and alternative mechanisms before writing a new typed proposal. "
            "Retests of a family on DIFFERENT parents are not equivalent experiments."
        ),
        "development_results_are_not_independent_replications": True,
        "development_mdd_windows_are_not_full_period_mdd": True,
        "evaluation_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        "source_learning_evidence_hash": validated_learning["evidence_hash"],
        "source_economic_history_hash": validated_economics["history_evidence_hash"],
        "evidence_hash": content_hash(proof),
        "automatic_strategy_execution": False,
        "causal_status": "NOT_ESTABLISHED",
        "independent_oos_approved": False,
        "broker_executable": False,
    }
