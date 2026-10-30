"""Evidence-bound, multi-lane GPT research direction contract (development only).

All completed outcomes are admissible as explanatory evidence, even failures.
This module only prepares a research decision and validates a GPT-authored next
hypothesis; it does not impersonate a model or silently submit generations.
"""
from __future__ import annotations

from hashlib import sha256
from math import isfinite
from typing import Any, Mapping, Sequence

from core.integrity.hashes import content_hash
from research.llm.guided_research_feedback import training_outcome

RESEARCH_MODES = frozenset({
    "EXPLORE", "DIAGNOSE_FAILURE", "REFINE_PARENT",
    "CONTRAST_PARENTS", "TEST_SINGLE_FACTOR",
})


def summarize_parent_outcomes(*, history: Sequence[Mapping[str, Any]],
                              controls: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Attribute verified child training deltas to exact, earlier signed parents.

    The caller supplies already hash-checked controlled reports; this routine
    additionally fails closed on broken ancestry or run alignment. Development
    comparisons are research feedback, NEVER promotion or OOS authorization.
    """
    if len(history) != len(controls):
        raise ValueError("PARENT_OUTCOME_CONTROL_INTEGRITY_MISMATCH")
    run_to_generation: dict[str, int] = {}
    outcomes: dict[str, dict[str, Any]] = {}
    for generation, (record, control) in enumerate(zip(history, controls, strict=True), 1):
        run_id = record.get("run_id")
        proposal = record.get("proposal")
        if (record.get("proposal_verified") is not True or not isinstance(run_id, str)
                or run_id in run_to_generation or not isinstance(proposal, Mapping)
                or control.get("generation") != generation
                or control.get("run_id") != run_id
                or control.get("sealed_oos_evaluated") is not False
                or control.get("orders_enabled") is not False):
            raise ValueError("PARENT_OUTCOME_RUN_INTEGRITY_MISMATCH")
        comparisons = control.get("comparisons")
        if not isinstance(comparisons, list) or len(comparisons) != 1:
            raise ValueError("PARENT_OUTCOME_COMPARISON_INTEGRITY_MISMATCH")
        delta = comparisons[0].get("net_total_return_delta")
        if isinstance(delta, bool) or not isinstance(delta, (float, int)) or not isfinite(delta):
            raise ValueError("PARENT_OUTCOME_DELTA_INTEGRITY_MISMATCH")
        ancestor = proposal.get("parent_run_id")
        if ancestor is not None:
            if not isinstance(ancestor, str) or ancestor not in run_to_generation:
                raise ValueError("PARENT_OUTCOME_ANCESTOR_INTEGRITY_MISMATCH")
            parent_key = str(run_to_generation[ancestor])
            stats = outcomes.setdefault(parent_key, {"gains": 0, "losses": 0, "ties": 0})
            label = "gains" if delta > 1e-9 else "losses" if delta < -1e-9 else "ties"
            stats[label] += 1
        run_to_generation[run_id] = generation
    return outcomes


def build_director_brief(*, session_id: str, generation: int,
                         checkpoint_token: str | None,
                         history: Sequence[Mapping[str, Any]],
                         learning: Mapping[str, Any],
                         controlled: Mapping[str, Any]) -> dict[str, Any]:
    """Pareto-aware lanes: positive, defensive, failure diagnostic and novelty.

    Scores for ranking parents are strictly from training fold returns, never
    validation/test/full-development returns. A failing candidate may appear in
    any lane when the exact precommitted IR is verified.
    """
    if type(generation) is not int or generation < 1:
        raise ValueError("DIRECTOR_INVALID_GENERATION")
    if len(session_id) != 32 or checkpoint_token is not None and not isinstance(checkpoint_token, str):
        raise ValueError("DIRECTOR_INVALID_SESSION_OR_TOKEN")
    pool: list[dict[str, Any]] = []
    for index, record in enumerate(history, 1):
        if not record.get("proposal_verified"):
            continue
        for candidate in record["attempt"].get("candidates", ()):
            train = training_outcome(record["attempt"], candidate)
            if not train["train_folds_observed"]:
                continue
            parent_hash = candidate.get("semantic_strategy_hash")
            if not isinstance(parent_hash, str) or len(parent_hash) != 64:
                continue
            pool.append({
                "generation": index, "semantic_strategy_hash": parent_hash,
                "family": candidate.get("family") or "UNCLASSIFIED",
                "train_return": train["training_only_return_mean"],
                "train_folds": train["train_folds_observed"],
                "failed_final_gates": list(candidate.get("failed_gates") or []),
                "production_approved": False,
                "exact_ir_required": True,
            })
    unique: dict[str, dict[str, Any]] = {}
    for entry in pool:
        unique.setdefault(entry["semantic_strategy_hash"], entry)
    pool = list(unique.values())
    # A high historical train score is not evidence of a productive parent
    # after multiple failed, immutable same-cost offspring comparisons.
    lineage = controlled.get("parent_outcomes") or {}
    def offspring_stats(entry: Mapping[str, Any]) -> tuple[int, int]:
        stats = lineage.get(str(entry["generation"]), {})
        return int(stats.get("gains", 0)), int(stats.get("losses", 0))

    def exhausted(entry: Mapping[str, Any]) -> bool:
        gains, losses = offspring_stats(entry)
        return gains == 0 and losses >= 3

    def research_priority(entry: Mapping[str, Any]) -> tuple[float, int]:
        gains, losses = offspring_stats(entry)
        # Smoothed observed offspring success, without peeking into test folds.
        success_rate = (gains + 1) / (gains + losses + 2)
        return -(entry["train_return"] * (0.5 + success_rate)), entry["generation"]

    by_return = sorted((x for x in pool if not exhausted(x)), key=research_priority)
    negative = sorted((p for p in pool if p["failed_final_gates"]),
                      key=lambda x: (exhausted(x), x["train_return"], x["generation"]))
    # Distinct families and distinct strategies remain eligible, even if losing.
    diverse: list[dict[str, Any]] = []
    seen_families: set[str] = set()
    for entry in sorted(pool, key=lambda x: x["generation"]):
        if entry["family"] not in seen_families:
            diverse.append(entry)
            seen_families.add(entry["family"])
    lanes = {
        "TRAIN_ONLY_PERFORMANCE": by_return[:3],
        "FAILED_HYPOTHESIS_REPAIR": negative[:3],
        "DISTINCT_FAMILY_EXPLORATION": diverse[:3],
    }
    # These are alternative hypotheses with multiple parents, not an untested
    # mixture of indicators or a fabricated crossover implementation.
    pairs: list[dict[str, Any]] = []
    for first in by_return:
        for other in diverse:
            if first["semantic_strategy_hash"] != other["semantic_strategy_hash"]:
                pairs.append({
                    "first_generation": first["generation"],
                    "alternative_generation": other["generation"],
                    "comparison_only": True,
                    "crossed_strategy_constructed": False,
                })
                break
        if len(pairs) == 2:
            break
    digest = content_hash({
        "schema": "guided-director-context-v1",
        "session_id": session_id,
        "generation": generation,
        "checkpoint_token_sha256": (sha256(checkpoint_token.encode()).hexdigest()
                                    if checkpoint_token is not None else None),
        "feedback_digest": learning.get("evidence_digest"),
        "training_controls": controlled.get("last_three_control_results", []),
        "parent_outcomes": lineage,
        "parent_pool": [{"generation":x["generation"],
                         "semantic_strategy_hash":x["semantic_strategy_hash"],
                         "train_return":x["train_return"]} for x in pool],
    })
    return {
        "schema": "guided-director-context-v1",
        "context_digest": digest,
        "next_generation": generation,
        "available_research_modes": sorted(RESEARCH_MODES),
        "parent_lanes": lanes,
        "repeated_loss_parent_generations": sorted(
            x["generation"] for x in pool if exhausted(x)
        ),
        "contrast_parent_pairs": pairs,
        "failed_candidates_considered": learning.get("failed_candidates_included", 0),
        "controlled_experiment_priority": controlled.get("next_experiment_priority"),
        "next_hypotheses": learning.get("suggested_controlled_hypotheses", [])[:4],
        "no_exact_parent_ir_available": not bool(pool),
        "decision_owner": "EXTERNAL_GPT_RESEARCH_DIRECTOR",
        "control_required": "UNCHANGED_PARENT_SAME_COSTS",
        "production_parent_promotion": False,
        "multiple_parent_guide_only": True,
        "sealed_oos_evaluated": False,
    }


def validate_director_decision(*, decision: Mapping[str, Any],
                               brief: Mapping[str, Any],
                               requested_parent_generation: int | None) -> dict[str, Any]:
    """Fail closed if a GPT plan is stale, unsupported or unproven.

    Parent choices remain optional. Selecting two comparison sources never
    authorizes applying a genetic crossover to an unverified child strategy.
    """
    if not isinstance(decision, dict) or set(decision) != {
        "schema", "context_digest", "research_mode", "hypothesis",
        "competing_explanation", "research_parent_generation",
        "contrast_parent_generation",
    }:
        raise ValueError("DIRECTOR_DECISION_SCHEMA_MISMATCH")
    if decision["schema"] != "guided-research-director-decision-v1":
        raise ValueError("DIRECTOR_DECISION_VERSION_MISMATCH")
    if decision["context_digest"] != brief.get("context_digest"):
        raise ValueError("DIRECTOR_STALE_FEEDBACK_CONTEXT")
    if decision["research_mode"] not in RESEARCH_MODES:
        raise ValueError("DIRECTOR_UNSUPPORTED_RESEARCH_MODE")
    for field in ("hypothesis", "competing_explanation"):
        value = decision[field]
        if not isinstance(value, str) or not (12 <= len(value.strip()) <= 1500):
            raise ValueError("DIRECTOR_UNTESTABLE_HYPOTHESIS")
    claimed = decision["research_parent_generation"]
    if claimed is not None and (type(claimed) is not int or not 1 <= claimed < brief["next_generation"]):
        raise ValueError("DIRECTOR_INVALID_PARENT")
    if claimed != requested_parent_generation:
        raise ValueError("DIRECTOR_PARENT_SELECTION_DISAGREES_WITH_EXECUTION")
    alternative = decision["contrast_parent_generation"]
    if alternative is not None:
        if (decision["research_mode"] != "CONTRAST_PARENTS"
            or type(alternative) is not int
            or not 1 <= alternative < brief["next_generation"]
            or alternative == claimed):
            raise ValueError("DIRECTOR_INVALID_CONTRAST")
    if decision["research_mode"] == "CONTRAST_PARENTS" and (alternative is None or claimed is None):
        raise ValueError("DIRECTOR_CONTRAST_REQUIRES_TWO_PRIOR_PARENTS")
    available = {x["generation"] for lane in brief["parent_lanes"].values() for x in lane}
    if claimed is not None and claimed not in available:
        raise ValueError("DIRECTOR_PARENT_NOT_IN_VERIFIED_TRAINING_LANES")
    if alternative is not None and alternative not in available:
        raise ValueError("DIRECTOR_CONTRAST_NOT_IN_VERIFIED_TRAINING_LANES")
    return dict(decision)
