"""T4 preregister random algorithm candidates before any measured execution.

No prices, research state, model API, account keys, or past GPT results are read.
This is an experimental cohort generator, not a trading strategy or optimizer.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

SEED = 20261016
INDICATORS = (
    "dual_sma_trend_50",
    "ema_direction_20",
    "previous_range_breakout",
    "range_low_reclaim_20",
    "sma_pullback_20",
    "time_series_momentum",
)
OUT = Path(
    "docs/operations/evidence/quant-validation-20261016/"
    "t4-random-10plan-preregister.json"
)


def generate() -> dict[str, Any]:
    rng = random.Random(SEED)
    plans = []
    for i in range(10):
        entry = rng.sample(INDICATORS, k=4)
        threshold = rng.choice((0.00010, 0.00013, 0.00015, 0.00018, 0.00020))
        branches = []
        for j, selected in enumerate((entry[:2], entry[2:])):
            weight = rng.choice((0.35, 0.40, 0.45, 0.5, 0.55, 0.6, 0.65))
            score_threshold = rng.choice((0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75))
            branches.append({
                "case_id": f"random_case_{j+1}",
                "when": {
                    "indicator_id": "parkinson_variance",
                    "op": "less_equal" if j == 0 else "greater_than",
                    "threshold": threshold,
                },
                "votes": [
                    {"indicator_id": selected[0], "weight": weight},
                    {"indicator_id": selected[1], "weight": round(1 - weight, 2)},
                ],
                "min_score": score_threshold,
            })
        plans.append({"plan_id": f"t4_rnd_g{i+1:02d}_seed20261016", "cases": branches})
    body = {
        "schema": "t4-preregistered-random-10plan-cohort-v1",
        "seed": SEED,
        "cohort_size": 10,
        "development_data_path": (
            "data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet"
        ),
        "development_data_expected_hash": (
            "328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6"
        ),
        "research_budget_per_arm": {
            "parent_plans": 10,
            "paired_s7_experiments": 10,
        },
        "preregistration_limitations": (
            "Plans are fixed before random-arm results; prior GPT-arm findings "
            "exist, so experiment design is not fully blind or preregistered "
            "relative to the GPT arm. Diagnosis is model-authored and distinct "
            "from independently generated random plans."
        ),
        "selected_indicators": list(INDICATORS),
        "plans": plans,
        "orders_enabled": False,
        "broker_executable": False,
        "pit_oos_evaluated": False,
    }
    body["cohort_sha256"] = hashlib.sha256(
        json.dumps(plans, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return body


def main() -> None:
    out = generate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        old = json.loads(OUT.read_text())
        if old != out:
            raise SystemExit("PRECOMMIT MISMATCH: existing plans must not be changed")
    else:
        with OUT.open("x", encoding="utf-8") as stream:
            json.dump(out, stream, sort_keys=True, indent=2)
            stream.write("\n")
    print(
        "T4 random precommit verified",
        f"seed={SEED}",
        f"plans={len(out['plans'])}",
        f"cohort_sha256={out['cohort_sha256']}",
    )


if __name__ == "__main__":
    main()
