"""P3-1: preregistered, equally budgeted model/random/local research arms.

Research-only development evidence. GPT intents arrive from recorded MCP
proposals; no fake model call, profit threshold tuning, sealed OOS access or
strategy promotion. One canonical parent and one fee model for all arms.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from math import isfinite
from pathlib import Path
from random import Random
from typing import Any

from core.data.contracts import DataZone, MarketDataSet
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from evaluation.academic_s7_risk_replay import fill_exposure
from evaluation.metrics import calculate_metrics
from research.indicator_engine.development_benchmark import compare_qqq_development_benchmarks
from research.indicator_engine.strategy_adapter import (
    AcademicDevelopmentResult,
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent


class FixedBudgetError(ValueError):
    """Invalid candidate preregistration or evidence identity."""


_ARMS = ("GPT_HISTORICAL", "RANDOM", "LOCAL_EVOLUTION")
_SCHEMA = "preregistered-three-arm-development-budget-p3-1-v1"
_ORIGINS = frozenset(
    {"HISTORICAL_UNVERIFIED", "DECLARED_CHATGPT_CLIENT_UNVERIFIED", "SCRIPTED_TEMPLATE"}
)


def _validate_parent(parent: CompiledAcademicStrategy, market: MarketDataSet) -> None:
    if market.zone != DataZone.DEVELOPMENT:
        raise FixedBudgetError("development-only market required")
    if (
        parent.dataset_hash != market.dataset_hash
        or parent.strategy_hash
        != content_hash(parent.strategy.model_dump(mode="json", by_alias=True))
        or parent.broker_executable is not False
        or parent.sealed_oos_approved is not False
    ):
        raise FixedBudgetError("parent strategy or dataset hash mismatch")


def _eligible_thresholds(parent: CompiledAcademicStrategy) -> list[tuple[str, Any, float, float]]:
    """Predefined reviewed, scalar, existing rule family; never new code or indicator."""
    checks = (
        [(f"entry.conditions.{i}", rule) for i, rule in enumerate(parent.strategy.entry.conditions)]
        + [(f"exit.conditions.{i}", rule) for i, rule in enumerate(parent.strategy.exit.conditions)]
        # Regime filter replacements require their own typed mutation contract.
        # The current control mutation uses REPLACE_RULE, which ONLY targets
        # entry/exit conditions. Never preregister an invalid regime mutation.
    )
    eligible = []
    for path, rule in checks:
        if rule.right is not None or not rule.enabled or not isinstance(rule.value, (int, float)):
            continue
        if rule.left == "parkinson_variance":
            lo, hi = 0.000025, 0.0002
        elif rule.left in {
            "plan_vote_score",
            "plan_entry",
            "plan_regime",
            "previous_range_breakout",
            "time_series_momentum",
            "ema_direction_20",
            "dual_sma_trend_50",
        }:
            lo, hi = 0.10, 0.90
        else:
            continue
        if rule.op not in {"greater_than", "less_equal", "greater_equal", "less_than"}:
            continue
        if not (isfinite(float(rule.value)) and lo <= float(rule.value) <= hi):
            continue
        eligible.append((path, rule, lo, hi))
    if not eligible:
        raise FixedBudgetError("parent has no supported predeclared mutation coordinate")
    return eligible


def _candidate_intent(
    parent: CompiledAcademicStrategy,
    item: tuple[str, Any, float, float],
    value: float,
    arm: str,
    number: int,
) -> ResearchIntent:
    path, condition, _lo, _hi = item
    replacement = condition.model_dump(mode="json")
    replacement["value"] = value
    return ResearchIntent.model_validate(
        {
            "mode": "structure",
            "parent_ids": [parent.strategy.strategy_id],
            "rationale": f"PREDECLARED_{arm}_POLICY_V1_SLOT_{number}_NOT_LLM",
            "operations": [{"op": "REPLACE_RULE", "path": path, "condition": replacement}],
        }
    )


def _generate_controls(
    parent: CompiledAcademicStrategy, budget: int, seed: int
) -> dict[str, list[ResearchIntent]]:
    coords = _eligible_thresholds(parent)
    rnd = Random(seed)
    result: dict[str, list[ResearchIntent]] = {"RANDOM": [], "LOCAL_EVOLUTION": []}
    for i in range(budget):
        # FIXED number of proposals; no rejection-resampling or best-of-K
        # hidden search. Each generated candidate uses one evaluation slot.
        selected = coords[rnd.randrange(len(coords))]
        lo, hi = selected[2], selected[3]
        value = lo + (hi - lo) * rnd.random()
        result["RANDOM"].append(_candidate_intent(parent, selected, value, "RANDOM", i))
        local = coords[i % len(coords)]
        llo, lhi = local[2], local[3]
        original = float(local[1].value)
        sign = 1 if i % 2 == 0 else -1
        closer = max(llo, min(lhi, original + sign * (lhi - llo) * 0.05))
        result["LOCAL_EVOLUTION"].append(
            _candidate_intent(parent, local, closer, "LOCAL_EVOLUTION", i)
        )
    return result


def build_fixed_budget_manifest(
    parent: CompiledAcademicStrategy,
    market: MarketDataSet,
    gpt_intents: list[ResearchIntent],
    *,
    seed: int,
    source_evidence_hash: str,
    research_origin: str = "HISTORICAL_UNVERIFIED",
) -> dict[str, Any]:
    """Freeze EVERY candidate identity before any outcome is measured."""
    _validate_parent(parent, market)
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**32:
        raise FixedBudgetError("invalid random seed")
    if not isinstance(source_evidence_hash, str) or len(source_evidence_hash) != 64:
        raise FixedBudgetError("missing GPT source evidence hash")
    if not 1 <= len(gpt_intents) <= 5:
        raise FixedBudgetError("candidate budget must be between 1 and 5 per arm")
    if research_origin not in _ORIGINS:
        raise FixedBudgetError("unsupported or certified model origin")
    controls = _generate_controls(parent, len(gpt_intents), seed)
    all_intents = {
        "GPT_HISTORICAL": gpt_intents,
        "RANDOM": controls["RANDOM"],
        "LOCAL_EVOLUTION": controls["LOCAL_EVOLUTION"],
    }
    rows: list[dict[str, Any]] = []
    seen_gpt: set[str] = set()
    for arm in _ARMS:
        for index, intent in enumerate(all_intents[arm]):
            if not isinstance(intent, ResearchIntent):
                raise FixedBudgetError("typed research intent required")
            if intent.feature_proposal or intent.primitive_request or intent.feature_selections:
                raise FixedBudgetError("unreviewed feature or new primitive not eligible")
            if not intent.operations:
                raise FixedBudgetError("no-op intent cannot consume an arm slot")
            child = apply_intent(parent.strategy, intent, research_feature_specs())
            fingerprint = content_hash(child.model_dump(mode="json", by_alias=True))
            if arm == "GPT_HISTORICAL":
                if fingerprint in seen_gpt:
                    raise FixedBudgetError("duplicate GPT candidate strategy")
                seen_gpt.add(fingerprint)
            rows.append(
                {
                    "candidate_id": f"{arm}-{index + 1}",
                    "arm": arm,
                    "slot": index + 1,
                    "intent": intent.model_dump(mode="json"),
                    "strategy_hash": fingerprint,
                    "origin": "PRIOR_GPT_MCP_RESEARCH_NOT_NEW_CALL"
                    if arm == "GPT_HISTORICAL"
                    else "DETERMINISTIC_RESEARCH_CONTROL_NO_MODEL",
                }
            )
    body: dict[str, Any] = {
        "schema": _SCHEMA,
        "parent_strategy_hash": parent.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "source_gpt_evidence_hash": source_evidence_hash,
        "research_origin": research_origin,
        "model_identity_verified": False,
        "adaptive_reasoning_verified": False,
        "gpt_arm_label_is_claim_not_authentication": True,
        "arm_names": list(_ARMS),
        "candidates_per_arm": len(gpt_intents),
        "random_seed": seed,
        "generation_count_increment": 0,
        "benchmark_outcome_not_yet_measured": True,
        "comparison_is_retrospective": True,
        "source_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        "policy_version": "RANDOM_UNIFORM_LOCAL_5PCT_RANGE_V1",
        "candidates": rows,
        "broker_executable": False,
        "independent_oos_approved": False,
    }
    return {**body, "freeze_hash": content_hash(body)}


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if not isinstance(manifest, dict):
        raise FixedBudgetError("missing manifest")
    body = {k: v for k, v in manifest.items() if k != "freeze_hash"}
    if (
        content_hash(body) != manifest.get("freeze_hash")
        or manifest.get("schema") != _SCHEMA
        or manifest.get("arm_names") != list(_ARMS)
        or manifest.get("policy_version") != "RANDOM_UNIFORM_LOCAL_5PCT_RANGE_V1"
        or manifest.get("source_scope") != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
        or manifest.get("research_origin") not in _ORIGINS
        or manifest.get("model_identity_verified") is not False
        or manifest.get("adaptive_reasoning_verified") is not False
        or manifest.get("gpt_arm_label_is_claim_not_authentication") is not True
        or manifest.get("broker_executable") is not False
        or manifest.get("independent_oos_approved") is not False
        or manifest.get("generation_count_increment") != 0
        or manifest.get("comparison_is_retrospective") is not True
    ):
        raise FixedBudgetError("frozen arm study hash, policy or scope mismatch")


def write_frozen_manifest(path: Path, manifest: dict[str, Any]) -> None:
    _validate_manifest(manifest)
    # Exclusive creation makes an already committed plan impossible to replace
    # through the intended CLI. Replay scorer also rejects content tampering.
    with path.open("x", encoding="utf-8") as out:
        json.dump(manifest, out, sort_keys=True, ensure_ascii=False, indent=2)
        out.write("\n")


def read_frozen_manifest(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    _validate_manifest(obj)
    if not isinstance(obj, dict):
        raise FixedBudgetError("manifest must be a JSON object")
    return obj


def _measure(result: AcademicDevelopmentResult, market: MarketDataSet) -> dict[str, Any]:
    m = calculate_metrics(result.equity_curve, (), periods_per_year=252)
    closed, exposure = fill_exposure(result.trades, market.bars)
    return {
        "strategy_hash": result.strategy_hash,
        "equity_hash": result.equity_hash,
        "total_return": m.total_return,
        "cagr": m.cagr,
        "sharpe": m.sharpe,
        "max_drawdown": m.max_drawdown,
        "market_exposure": exposure,
        "closed_trades": closed,
        "fill_count": result.trades_count,
        "transaction_costs": result.total_paid_costs,
        "final_equity": result.final_equity,
    }


def score_frozen_budget(
    parent: CompiledAcademicStrategy,
    market: MarketDataSet,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Exactly K canonical simulations per arm, no hidden retry/tuning."""
    _validate_parent(parent, market)
    _validate_manifest(manifest)
    if (
        manifest["dataset_hash"] != market.dataset_hash
        or manifest["parent_strategy_hash"] != parent.strategy_hash
    ):
        raise FixedBudgetError("frozen parent/dataset strategy mismatch")
    gpt = [
        ResearchIntent.model_validate(item["intent"])
        for item in manifest["candidates"]
        if item["arm"] == "GPT_HISTORICAL"
    ]
    try:
        expected = build_fixed_budget_manifest(
            parent,
            market,
            gpt,
            seed=manifest["random_seed"],
            source_evidence_hash=manifest["source_gpt_evidence_hash"],
            research_origin=manifest["research_origin"],
        )
    except (ValueError, TypeError) as exc:
        raise FixedBudgetError("frozen candidate regeneration failed") from exc
    if manifest != expected:
        raise FixedBudgetError("frozen study integrity: regenerated controls differ")
    count = manifest["candidates_per_arm"]
    if len(manifest["candidates"]) != 3 * count:
        raise FixedBudgetError("unequal fixed arm budget")
    parent_result = evaluate_compiled_development(parent, market)
    parent_measure = _measure(parent_result, market)
    benchmark = compare_qqq_development_benchmarks(market)["qqq_costed_buy_and_hold"]
    outcomes = []
    for item in manifest["candidates"]:
        intent = ResearchIntent.model_validate(item["intent"])
        ir = apply_intent(parent.strategy, intent, research_feature_specs())
        fingerprint = content_hash(ir.model_dump(mode="json", by_alias=True))
        if fingerprint != item["strategy_hash"]:
            raise FixedBudgetError("child hash changed since preregistration")
        actual = evaluate_compiled_development(
            replace(parent, strategy=ir, strategy_hash=fingerprint), market
        )
        measured = _measure(actual, market)
        outcomes.append(
            {
                "arm": item["arm"],
                "candidate_id": item["candidate_id"],
                "source_candidate_strategy_hash": fingerprint,
                "measured": measured,
                "parent_net_equity_delta": measured["final_equity"]
                - parent_measure["final_equity"],
                "parent_max_drawdown_delta": measured["max_drawdown"]
                - parent_measure["max_drawdown"],
                "qqq_buy_hold_return_delta": measured["total_return"] - benchmark["total_return"],
                "costs_included_in_equity": True,
                "same_fill_trace_as_parent": actual.trades == parent_result.trades,
                "same_equity_curve_as_parent": actual.equity_curve == parent_result.equity_curve,
            }
        )
    ranks = []
    for arm in _ARMS:
        rows = [x for x in outcomes if x["arm"] == arm]
        if len(rows) != count:
            raise FixedBudgetError("unbalanced arm outcomes")
        ranks.append(
            {
                "arm": arm,
                "evaluations": len(rows),
                "positive_net_equity_delta": sum(x["parent_net_equity_delta"] > 1e-8 for x in rows),
                "no_worse_mdd_and_better_return": sum(
                    x["parent_net_equity_delta"] > 1e-8 and x["parent_max_drawdown_delta"] <= 1e-9
                    for x in rows
                ),
                "mean_total_return": sum(x["measured"]["total_return"] for x in rows) / count,
                "mean_max_drawdown": sum(x["measured"]["max_drawdown"] for x in rows) / count,
                "mean_market_exposure": sum(x["measured"]["market_exposure"] for x in rows) / count,
                "mean_paid_costs": sum(x["measured"]["transaction_costs"] for x in rows) / count,
                "unique_child_strategies": len({x["measured"]["strategy_hash"] for x in rows}),
                "same_fill_trace_as_parent_count": sum(
                    x["same_fill_trace_as_parent"] for x in rows
                ),
            }
        )
    all_hashes = Counter(x["measured"]["strategy_hash"] for x in outcomes)
    body = {
        "schema": "three-arm-canonical-research-measurements-p3-1-v1",
        "frozen_study_hash": manifest["freeze_hash"],
        "source_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        "research_origin": manifest["research_origin"],
        "model_identity_verified": False,
        "adaptive_reasoning_verified": False,
        "parent": parent_measure,
        "benchmark": {
            "costed_qqq_buy_and_hold_return": benchmark["total_return"],
            "basis": benchmark["basis"],
            "dividends_reinvested": False,
            "independent_oos_approved": False,
        },
        "arms": ranks,
        "trials": outcomes,
        "candidate_evaluations": len(outcomes),
        "baseline_evaluations": 1,
        "arm_evaluations_equal": True,
        "cross_arm_duplicate_candidate_hashes": sum(n - 1 for n in all_hashes.values()),
        "selection_bias_notice": (
            "Historical GPT proposal is preselected from reused development data"
        ),
        "budget_is_test_count_not_token_or_compute_cost_equivalence": True,
        "statistical_superiority_established": False,
        "automatic_parent_promotion": False,
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    return {**body, "report_hash": content_hash(body)}
