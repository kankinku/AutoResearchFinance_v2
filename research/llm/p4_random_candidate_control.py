"""T4 diagnostic: fixed-seed random S2 candidate slots plus one S7 placebo each.

NOT a matched randomized autonomous LLM campaign: no provider calls, feedback
evolution, P3 parent inheritance, or claim that a candidate slot is a generation.
Use *one* predeclared seed and ten slots, report duplicates/flat candidates without
replacement or post-hoc seed search. Only verified catalog primitives are used.
"""

from __future__ import annotations

from random import Random
from typing import Any, cast

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    compile_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.controlled_experiments import compare_controlled_experiments
from research.indicator_engine.models import BINARY_ENTRY_CALCULATORS
from research.llm.diagnostic_research import build_diagnostic_context


def _semantic_plan(plan: AlgorithmPlan) -> dict[str, Any]:
    data = plan.model_dump(mode="json")
    data.pop("plan_id")
    return data


def generate_random_candidate_plans(
    catalog: ResearchCatalog,
    *,
    count: int = 10,
    seed: int = 20261024,
) -> tuple[AlgorithmPlan, ...]:
    """Draw a frozen *candidate-count* reference independent of return data.

    This has no performance-based redraw or reselection. Only exact structural
    collisions redraw, bounded to avoid silently expanding the search budget.
    """
    if (
        type(count) is not int
        or not 1 <= count <= 10
        or type(seed) is not int
        or not 0 <= seed < 2**32
    ):
        raise ValueError("random candidate count or reproducibility seed invalid")
    eligible = catalog.list_indicators(eligible_only=True)
    gates = tuple(
        x
        for x in eligible
        if (
            x.scope == "single_asset"
            and x.execution_delay_bars == 1
            and x.role in ("risk", "regime")
        )
    )
    votes = tuple(
        x
        for x in eligible
        if (
            x.scope == "single_asset"
            and x.execution_delay_bars == 1
            and x.role == "entry"
            and x.calculator in BINARY_ENTRY_CALCULATORS
        )
    )
    if not gates or len(votes) < 2:
        raise ResearchCatalogError(
            "verified random reference requires risk/regime and two entry votes"
        )
    rng = Random(seed)
    created: list[AlgorithmPlan] = []
    observed: set[str] = set()
    for index in range(count):
        accepted = False
        for _ in range(128):
            num_cases = rng.choice((1, 2))
            cases = []
            for case_index in range(num_cases):
                gate = rng.choice(gates)
                threshold = (
                    0.5
                    if gate.calculator in ("sma_direction",)
                    else rng.choice((0.000025, 0.0001, 0.0004))
                )
                selected = rng.sample(votes, rng.choice((1, 2)))
                case_votes = [
                    {"indicator_id": item.signal_id, "weight": rng.choice((0.5, 1.0, 2.0))}
                    for item in selected
                ]
                cases.append(
                    {
                        "case_id": f"branch_{case_index + 1:02d}",
                        "when": {
                            "indicator_id": gate.signal_id,
                            "op": rng.choice(("greater_than", "less_equal")),
                            "threshold": threshold,
                        },
                        "votes": case_votes,
                        "min_score": rng.choice((0.5, 0.75, 1.0)),
                    }
                )
            plan = AlgorithmPlan.model_validate(
                {
                    "plan_id": f"random_candidate_{index + 1:02d}",
                    "cases": cases,
                    "unmatched": "FLAT",
                    "position_size_pct": 100,
                }
            )
            signature = content_hash(_semantic_plan(plan))
            if signature in observed:
                continue
            observed.add(signature)
            created.append(plan)
            accepted = True
            break
        if not accepted:
            raise ResearchCatalogError(
                "failed to sample distinct random plans within fixed attempts"
            )
    return tuple(created)


def evaluate_random_candidate_cohort(
    catalog: ResearchCatalog,
    market: MarketDataSet,
    plans: tuple[AlgorithmPlan, ...],
    *,
    seed: int,
) -> dict[str, Any]:
    """One canonical costed S2 + one fixed S7 ablation attempt for each slot.

    No feedback mutations, no candidate filters, and no automatic replacement
    of inactive plans: a failed slot consumes that *candidate* opportunity.
    """
    if (
        type(seed) is not int
        or seed < 0
        or seed >= 2**32
        or not 1 <= len(plans) <= 10
        or market.zone != DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or len(market.bars) < 100
        or market.bars[-1].timestamp.year > 2025
        or any(x.symbol != "QQQ" for x in market.bars)
    ):
        raise ResearchCatalogError("random comparator requires fixed pre-2026 QQQ development data")
    semantic = [content_hash(_semantic_plan(p)) for p in plans]
    if len(semantic) != len(set(semantic)):
        raise ValueError("duplicate semantic random plans in fixed candidate cohort")
    collected = []
    for index, plan in enumerate(plans, 1):
        compiled = compile_algorithm_plan(catalog, plan, market)
        audit = audit_algorithm_plan(catalog, compiled, market)
        packet = build_diagnostic_context(audit, compiled.compiled.strategy)
        samples = cast(dict[str, Any], packet["observations"])["execution_samples"]
        if samples:
            # Predeclared single-change placebo (same across all slots).
            # This provides identical S7 attempt *count*, NOT LLM adaptation.
            hypothesis = {
                "context_hash": packet["context_hash"],
                "audit_hash": packet["audit_hash"],
                "strategy_hash": packet["strategy_hash"],
                "dataset_hash": packet["dataset_hash"],
                "summary": "Mechanical placebo: reduce sizing independent of market results.",
                "hypotheses": [
                    {
                        "hypothesis_id": f"random_sizing_{index:02d}",
                        "observed_ids": [samples[0]["trade_id"]],
                        "mechanism": "Reducing allocation mechanically changes portfolio exposure.",
                        "alternative": "Lower allocation can reduce gains as well as drawdown.",
                        "expected_metric": "max_drawdown",
                        "predicted_direction": "DECREASE",
                        "test_design": "PARAMETER",
                        "control": "PARENT_UNCHANGED",
                        "next_intent": {
                            "mode": "parameter",
                            "parent_ids": [compiled.compiled.strategy.strategy_id],
                            "operations": [
                                {
                                    "op": "CHANGE_POSITION_SIZE",
                                    "path": "risk.position_size_pct",
                                    "value": 70.0,
                                }
                            ],
                            "rationale": "One fixed mechanically reduced-size comparison.",
                        },
                    }
                ],
            }
            report = compare_controlled_experiments(catalog, compiled, market, hypothesis)
            s7_status = "MEASURED"
            s7_result = report.experiments[0].status
            s7_hash = report.evidence_hash
        else:
            # Validated and counted as an S7 attempt, but no real trade exists
            # from which to cite an observed ID. Never fabricate one.
            s7_status = "NOT_EXECUTABLE_NO_OBSERVED_TRADE"
            s7_result = None
            s7_hash = None
        collected.append(
            {
                "slot": index,
                "plan": plan.model_dump(mode="json"),
                "semantic_plan_hash": semantic[index - 1],
                "strategy_hash": compiled.compiled.strategy_hash,
                "s2_audit_hash": audit.trace_hash,
                "s2_equity_hash": audit.evaluation.equity_hash,
                "s2_total_return": audit.evaluation.final_equity / audit.evaluation.initial_cash
                - 1,
                "s2_mdd": cast(dict[str, Any], audit.llm_packet["metrics"])["max_drawdown"],
                "s2_closed_trades": len(audit.round_trips),
                "s2_costs_paid": audit.evaluation.total_paid_costs,
                "s7_attempt_status": s7_status,
                "s7_result_status": s7_result,
                "s7_evidence_hash": s7_hash,
            }
        )
    body = {
        "schema": "p4-t4-random-candidate-slot-control-v1",
        "generator": "FIXED_SEED_TYPED_VERIFIED_INDICATORS_TWO_BRANCH_MAX",
        "seed": seed,
        "candidate_slots_requested": len(plans),
        "candidate_s2_completed": len(collected),
        "s7_attempt_slots": len(collected),
        "s7_measured_count": sum(x["s7_attempt_status"] == "MEASURED" for x in collected),
        "dataset_hash": market.dataset_hash,
        "evaluation": "CANONICAL_NEXT_OPEN_AUDITED_DEVELOPMENT",
        "cost_policy": "academic-research-cost-v1",
        "random_controls_are_full_generations": False,
        "random_controls_have_parent_inheritance": False,
        "real_llm_generations": 0,
        "selection_bias_notice": "ONE_SEED_EX_POST_DEVELOPMENT_DESCRIPTIVE_ONLY",
        "candidates": collected,
        "broker_executable": False,
        "independent_oos_approved": False,
        "autonomy_proven": False,
    }
    return {**body, "report_hash": content_hash(body)}
