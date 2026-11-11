"""Freeze matched 10+10+10 AlgorithmPlan candidate identities before control tests.

GPT proposals are previously measured, hence this is RETROSPECTIVE-GPT with
prospectively frozen random/local controls, not independent model superiority.
No backtests/data/LLM API/broker access, and no operator can cherry-pick controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from random import Random
from typing import Any

from core.integrity.hashes import content_hash as _fresh_hash
from research.indicator_engine.algorithm_plan import AlgorithmPlan

ENTRIES = (
    "dual_sma_trend_50",
    "ema_direction_20",
    "previous_range_breakout",
    "range_low_reclaim_20",
    "sma_pullback_20",
    "time_series_momentum",
)
REGIMES = ("parkinson_variance", "sma_direction")
SEED = 20261020
GPT_SESSION = "30da9a29502d4bf2a67e014358dab2e9"
MARKET_HASH = "328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6"
SCHEMA = "T4_EQUAL_ALGORITHM_PLAN_OPPORTUNITY_V1"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def one_case(
    i: int,
    rid: str,
    gate_id: str,
    threshold: float,
    choice: list[str],
    weights: list[float],
    score: float,
    *,
    upper: bool,
) -> dict[str, Any]:
    return {
        "case_id": f"{rid}_{i}",
        "when": {
            "indicator_id": gate_id,
            "op": "greater_than" if upper else "less_equal",
            "threshold": threshold,
        },
        "votes": [
            {"indicator_id": n, "weight": round(w, 5)} for n, w in zip(choice, weights, strict=True)
        ],
        "min_score": round(score, 5),
    }


def random_plan(rng: Random, i: int) -> dict[str, Any]:
    gate = rng.choice(REGIMES)
    pivot = 0.5 if gate == "sma_direction" else round(rng.uniform(0.00008, 0.00025), 8)
    n = rng.choice((1, 2))
    cases = []
    for c in range(n):
        qty = rng.choice((2, 3))
        names = rng.sample(ENTRIES, qty)
        weights = [rng.uniform(0.2, 0.85) for _ in names]
        score = rng.uniform(0.55, 0.95)
        cases.append(
            one_case(
                c + 1,
                "rand",
                gate,
                pivot,
                names,
                weights,
                score,
                upper=(c == 1 if n == 2 else rng.choice((True, False))),
            )
        )
    return {
        "plan_id": f"t4_random_{i:02d}",
        "cases": cases,
        "unmatched": "FLAT",
        "position_size_pct": 100,
    }


def local_plan(i: int) -> dict[str, Any]:
    """Outcome-blind, deterministic neighborhood around a declared trend seed."""
    # Predefined independent trend/volatility prior, not derived from GPT trials.
    cutoff = (0.00010, 0.00015, 0.00020, 0.00025, 0.00018)[i % 5]
    lo_votes = (
        ["dual_sma_trend_50", "time_series_momentum"],
        ["ema_direction_20", "dual_sma_trend_50", "time_series_momentum"],
        ["dual_sma_trend_50", "sma_pullback_20", "time_series_momentum"],
    )[i % 3]
    hi_votes = (
        ["previous_range_breakout", "ema_direction_20"],
        ["dual_sma_trend_50", "ema_direction_20"],
        ["range_low_reclaim_20", "previous_range_breakout", "ema_direction_20"],
    )[i % 3]
    lo_w = [0.6, 0.4] if len(lo_votes) == 2 else [0.4, 0.35, 0.25]
    hi_w = [0.55, 0.45] if len(hi_votes) == 2 else [0.25, 0.5, 0.25]
    score = (0.6, 0.7, 0.8, 0.9, 0.75)[i % 5]
    return {
        "plan_id": f"t4_local_{i:02d}",
        "cases": [
            one_case(1, "local", "parkinson_variance", cutoff, lo_votes, lo_w, score, upper=False),
            one_case(2, "local", "parkinson_variance", cutoff, hi_votes, hi_w, score, upper=True),
        ],
        "unmatched": "FLAT",
        "position_size_pct": 100,
    }


def freeze(existing: dict[str, Any], *, seed: int = SEED) -> dict[str, Any]:
    assert existing["schema"] == "T4_CONNECTED_CHATGPT_10GEN_DEVELOPMENT_AUDIT_V1"
    assert existing["session_id"] == GPT_SESSION
    assert existing["dataset_hash"] == MARKET_HASH
    assert existing["generation_evidence_chain_valid"] is True
    assert existing["final_report"]["generations_completed"] == 10
    gpt_rows = existing["generations"]
    assert len(gpt_rows) == 10
    gpt = [AlgorithmPlan.model_validate(g["plan"]).model_dump(mode="json") for g in gpt_rows]
    assert len({digest(p) for p in gpt}) == 10
    rng = Random(seed)
    controls = {
        "RANDOM": [
            AlgorithmPlan.model_validate(random_plan(rng, i)).model_dump(mode="json")
            for i in range(1, 11)
        ],
        "LOCAL": [
            AlgorithmPlan.model_validate(local_plan(i)).model_dump(mode="json")
            for i in range(1, 11)
        ],
    }
    # Verify all arms share exactly the same approved indicator and typed syntax.
    allowed = set(ENTRIES + REGIMES)
    for _arm, rows in (("GPT_RECORDED", gpt), *controls.items()):
        for plan in rows:
            for case in plan["cases"]:
                assert case["when"]["indicator_id"] in REGIMES
                assert all(v["indicator_id"] in ENTRIES for v in case["votes"])
                assert len({v["indicator_id"] for v in case["votes"]}) == len(case["votes"])
                assert all(v["indicator_id"] in allowed for v in case["votes"])
    body = {
        "schema": SCHEMA,
        "source_gpt_session": GPT_SESSION,
        "gpt_prior_outcomes_visible": True,
        "design": "GPT_RETROSPECTIVE_RANDOM_LOCAL_PREREGISTERED",
        "dataset_hash": MARKET_HASH,
        "market": "QQQ_RAW_2020-2025_DEVELOPMENT_NON_PIT",
        "model": "EXISTING_ALGORITHM_PLAN_V1_NOT_GENERAL_PLAN",
        "arm_size": 10,
        "controlled_tests_per_generation": 1,
        "random_seed": seed,
        "approved_regime_indicators": REGIMES,
        "approved_entry_indicators": ENTRIES,
        "allocation": "100_PCT_LONG_FLAT",
        "entry_and_exit_execution": "CANONICAL_NEXT_OPEN_SAME_FEES",
        "scoring_preset": {
            "primary": "MEDIAN_COSTED_TOTAL_RETURN",
            "secondary": [
                "MEDIAN_FULL_PERIOD_MDD",
                "PASS_COUNT_GATES",
                "MEDIAN_SHARPE",
                "MEDIAN_CLOSED_TRADES",
                "BEST_DEVELOPMENT_RETURN",
            ],
            "pass_gates": {
                "positive_return": True,
                "mdd_lte": 0.2,
                "min_closed_trades": 10,
                "sharpe_gt": 0.5,
            },
            "inferential_claim": "NONE_TEN_TRIALS_NONPIT_AND_RETROSPECTIVE_MODEL",
        },
        "plans": {"GPT_RECORDED": gpt, **controls},
        "gpt_source_generation_evidence_hashes": [g["evidence_hash"] for g in gpt_rows],
        "gpt_history_hash": digest(gpt_rows),
        "control_result_not_yet_observed": True,
        "no_live_orders": True,
        "no_parent_promotion": True,
    }
    return {**body, "freeze_hash": digest(body)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpt-evidence", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fresh-protocol-output", type=Path)
    parser.add_argument("--fresh-manifest-config", type=Path)
    parser.add_argument("--fresh-manifest-output", type=Path)
    args = parser.parse_args()
    if args.fresh_protocol_output is not None:
        if any((args.gpt_evidence, args.output, args.fresh_manifest_config,
                args.fresh_manifest_output)):
            parser.error("fresh protocol may not be combined with historic inputs")
        content = fresh_three_arm_protocol()
        target = args.fresh_protocol_output
        signature = content["protocol_hash"]
    elif args.fresh_manifest_config is not None or args.fresh_manifest_output is not None:
        if (
            args.fresh_manifest_config is None or args.fresh_manifest_output is None
            or args.gpt_evidence is not None or args.output is not None
        ):
            parser.error("fresh manifest requires its own config and output")
        config = json.loads(args.fresh_manifest_config.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            parser.error("fresh manifest configuration must be an object")
        content = freeze_fresh_manifest(fresh_three_arm_protocol(), **config)
        target = args.fresh_manifest_output
        signature = content["freeze_hash"]
    else:
        if args.gpt_evidence is None or args.output is None:
            parser.error("historical comparison requires GPT evidence and output")
        evidence = json.loads(args.gpt_evidence.read_text())
        content = freeze(evidence)
        target = args.output
        signature = content["freeze_hash"]
    with target.open("x", encoding="utf-8") as stream:
        json.dump(content, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write("\n")
    if args.fresh_protocol_output is None and args.fresh_manifest_config is None:
        print("FROZEN", signature, "ARM_SIZE", content["arm_size"])
    else:
        print("FRESH_FROZEN", signature)


# v2 is deliberately separate from the 2026-10-20 RETROSPECTIVE GPT study.
# Reusing those ten measured GPT plans in a newly named G1 cohort is forbidden.

FRESH_SCHEMA = "T4_FRESH_EQUAL_BUDGET_PROTOCOL_V2"
FRESH_MANIFEST_SCHEMA = "T4_FRESH_EQUAL_BUDGET_MANIFEST_V2"
FRESH_ARMS = ("GPT_S7_S8", "FIXED_RULE", "RANDOM_SEEDED")
_OLD_SESSIONS = frozenset({
    GPT_SESSION,
    "14626d55fb2b461faa485df911920071",
})


class FreshProtocolError(ValueError):
    """The new G1 research must not begin with unbound or old trial inputs."""


def fresh_three_arm_protocol() -> dict[str, Any]:
    """Pre-data protocol: no historical GPT runs or market evidence are loaded."""
    body: dict[str, Any] = {
        "schema": FRESH_SCHEMA,
        "status": "BLOCKED_UNTIL_FRESH_MARKET_AND_SESSIONS",
        "arms": list(FRESH_ARMS),
        "generation_start": 1,
        "seed": 20261110,
        "budget_per_arm": {
            "plan_attempts": 10,
            "s7_trials": 10,
            "canonical_backtests": 20,
            "model_call_ceiling": 20,
            "model_token_ceiling": 200000,
        },
        "methods": {
            "GPT_S7_S8": "GPT_PLAN_DIAGNOSIS_S7_S8_FRESH_SESSION",
            "FIXED_RULE": "EXISTING_DETERMINISTIC_RULES_NO_OUTCOME_TUNING",
            "RANDOM_SEEDED": "PREREGISTERED_SEEDED_RANDOM_NO_OUTCOME_TUNING",
        },
        "selection_metric": "UNIQUE_COSTED_FILL_TRACE_WITH_RISK_GATES",
        "approved_entry_indicators": list(ENTRIES),
        "approved_regime_indicators": list(REGIMES),
        "common_symbol": "QQQ",
        "common_long_flat_next_open_cost_model": True,
        "risk_gates": {
            "minimum_closed_trades": 30,
            "max_drawdown": 0.30,
            "require_positive_net_return": True,
        },
        "statistics": {
            "claim_of_superiority": "NOT_PERMITTED_WITHOUT_INDEPENDENT_TRIALS",
            "one_seed_insufficient_for_statistical_significance": True,
            "reused_development_data_not_independent_oos": True,
        },
        "model_resource_policy": (
            "LOG_ACTUAL_REQUESTS_INPUT_OUTPUT_TOKENS_AND_DURATION_BY_ARM; "
            "EXPOSURE_UNBALANCED_IF_USAGE_DIFFERS; NEVER_INFER_EQUAL_MODEL_BUDGET"
        ),
        "immutable_manifest_requires_external_commit_before_first_outcome": True,
        "observation_and_submission_receipts_require_external_sha256_anchors": True,
        "past_cohort_reused": False,
        "no_parent_promotion": True,
        "orders_enabled": False,
        "independent_oos_approved": False,
    }
    return {**body, "protocol_hash": _fresh_hash(body)}


def _hex_hash(value: object, size: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == size
        and all(letter in "0123456789abcdef" for letter in value)
    )


def freeze_fresh_manifest(
    protocol: dict[str, Any],
    *,
    market_hash: str,
    evaluator_version: str,
    cost_policy_hash: str,
    feature_policy_hash: str,
    cohort_id: str,
    session_ids: dict[str, str],
    market_start: str,
    market_end: str,
    source_code_hash: str,
) -> dict[str, Any]:
    """Bind a NEW three-arm G1 study before any candidate outcome is examined.

    Save freeze_hash as an independent, immutable pre-run commit anchor.
    This function creates NO accounts, sessions, research scores, or orders.
    """
    if protocol != fresh_three_arm_protocol():
        raise FreshProtocolError("approved fresh protocol or its hash changed")
    if not all(_hex_hash(value) for value in (
        market_hash, cost_policy_hash, feature_policy_hash, source_code_hash
    )):
        raise FreshProtocolError("fresh market/cost/features/source SHA256 identities required")
    if (
        not isinstance(evaluator_version, str)
        or not evaluator_version.startswith("quant-improved-evaluator-")
        or not isinstance(cohort_id, str)
        or not cohort_id.startswith("fresh-")
        or len(cohort_id) < 7
    ):
        raise FreshProtocolError("new evaluator or fresh cohort identity missing")
    try:
        start, end = date.fromisoformat(market_start), date.fromisoformat(market_end)
        if str(start) != market_start or str(end) != market_end or start >= end:
            raise FreshProtocolError("development market window must be a fixed date range")
    except (TypeError, ValueError) as exc:
        raise FreshProtocolError("development market date range is invalid") from exc
    if (
        not isinstance(session_ids, dict)
        or set(session_ids) != set(FRESH_ARMS)
        or len(set(session_ids.values())) != 3
        or any(
            not _hex_hash(value, 32) or value in _OLD_SESSIONS
            for value in session_ids.values()
        )
    ):
        raise FreshProtocolError("distinct genuinely new G1 sessions required")
    body: dict[str, Any] = {
        "schema": FRESH_MANIFEST_SCHEMA,
        "protocol_hash": protocol["protocol_hash"],
        "cohort_id": cohort_id,
        "start_at_generation": 1,
        "dataset_hash": market_hash,
        "dataset_zone": "DEVELOPMENT",
        "market_window": {"start": market_start, "end": market_end},
        "source_code_hash": source_code_hash,
        "evaluator_version": evaluator_version,
        "cost_policy_hash": cost_policy_hash,
        "feature_policy_hash": feature_policy_hash,
        "session_ids": dict(session_ids),
        "budget_per_arm": dict(protocol["budget_per_arm"]),
        "random_seed": protocol["seed"],
        "selection_metric": protocol["selection_metric"],
        "risk_gates": dict(protocol["risk_gates"]),
        "old_sessions_prohibited": True,
        "actual_live_gpt_work_done": False,
        "requires_precommit_before_observation": True,
        "broker_executable": False,
        "independent_oos_approved": False,
    }
    return {**body, "freeze_hash": _fresh_hash(body)}


if __name__ == "__main__":
    main()
