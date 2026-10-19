"""Freeze matched 10+10+10 AlgorithmPlan candidate identities before control tests.

GPT proposals are previously measured, hence this is RETROSPECTIVE-GPT with
prospectively frozen random/local controls, not independent model superiority.
No backtests/data/LLM API/broker access, and no operator can cherry-pick controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from random import Random
from typing import Any

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
    parser.add_argument("--gpt-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads(args.gpt_evidence.read_text())
    content = freeze(evidence)
    with args.output.open("x") as stream:
        json.dump(content, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("FROZEN", content["freeze_hash"], "ARM_SIZE", content["arm_size"])


if __name__ == "__main__":
    main()
