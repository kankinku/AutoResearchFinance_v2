"""Run the pre-registered ten candidate-slot random reference on P4 DEVELOPMENT.

This is an independent isolated *reference*, NOT GPT generations, not equal
compute-time/model-call budget, and not a causal estimate of LLM improvement.
Never changes source counted sessions or provider credentials.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from statistics import mean, median
from tempfile import TemporaryDirectory
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog
from research.llm.p4_random_candidate_control import (
    evaluate_random_candidate_cohort,
    generate_random_candidate_plans,
)
from scripts.quant_p4_verify_10gen import verify

_FIXED_SEED = 20261024
_FIXED_SLOTS = 10


def run(root: Path, state: Path, session_id: str) -> dict[str, Any]:
    root, state = root.resolve(), state.resolve()
    source = verify(root, state, session_id)
    if source["orders_enabled"] or source["independent_oos_approved"]:
        raise ValueError("unsafe source controls")
    market = ParquetDataProvider.read(
        root / "data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet"
    )
    if market.dataset_hash != source["dataset_hash"]:
        raise ValueError("source and control data hashes differ")
    with TemporaryDirectory(prefix="t4-random-control-precommitted-") as ephemeral:
        catalog_path = Path(ephemeral) / "catalog.sqlite"
        original = state / "academic-gpt-checkpoints" / "catalog-s6-v2.sqlite"
        with sqlite3.connect(original.as_uri() + "?mode=ro", uri=True) as reader:
            with sqlite3.connect(catalog_path) as writer:
                reader.backup(writer)
        catalog = ResearchCatalog(catalog_path)
        plans = generate_random_candidate_plans(
            catalog, count=_FIXED_SLOTS, seed=_FIXED_SEED,
        )
        result = evaluate_random_candidate_cohort(
            catalog, market, plans, seed=_FIXED_SEED,
        )
    if (result["candidate_s2_completed"] != _FIXED_SLOTS
        or result["s7_attempt_slots"] != _FIXED_SLOTS
        or len(result["candidates"]) != _FIXED_SLOTS):
        raise ValueError("random candidate/S7 slot budget incomplete")
    original_after = verify(root, state, session_id)
    if source != original_after:
        raise ValueError("P4 original ledger changed during comparison")
    random_returns = [x["s2_total_return"] for x in result["candidates"]]
    gpt_returns = [x["total_return_pct"] / 100 for x in source["measured_generations"]]
    report = {
        "schema": "t4-preregistered-10slot-random-vs-gpt-descriptive-v1",
        "source_p4_report_hash": source["report_hash"],
        "dataset_hash": market.dataset_hash,
        "generator_commit": "83d164b",
        "seed": _FIXED_SEED,
        "counted_gpt_generations": 10,
        "random_s2_candidate_slots": _FIXED_SLOTS,
        "random_s7_attempt_slots": _FIXED_SLOTS,
        "random_s7_measured_count": result["s7_measured_count"],
        "random_best_return": max(random_returns),
        "random_median_return": median(random_returns),
        "random_mean_return": mean(random_returns),
        "gpt_best_return": max(gpt_returns),
        "gpt_median_return": median(gpt_returns),
        "gpt_mean_return": mean(gpt_returns),
        "qqq_costed_bh_return": source["qqq_costed_buy_and_hold_return_pct"] / 100,
        "random_positive_candidates": sum(x > 0 for x in random_returns),
        "random_qqq_exceedances": sum(
            x > source["qqq_costed_buy_and_hold_return_pct"] / 100 for x in random_returns
        ),
        "random_candidate_report": result,
        "outcome": "DESCRIPTIVE_ONLY_NOT_AN_EQUAL_AUTONOMOUS_GENERATION_CAUSAL_TEST",
        "limitations": [
            "P4 G9-G10 inherited parents; random candidates are independent",
            "P4 GPT hypotheses are adaptive; random S7 is a fixed sizing placebo",
            "Candidate/S7 attempt counts matched but model calls/time/selection budget not matched",
            "One preregistered random seed cannot estimate a null distribution",
            "Full 2020-2025 data reused for all candidates and comparison",
            "2026 previously examined elsewhere; never independent OOS here",
            "External GPT model invocation provenance missing",
        ],
        "random_measures_are_gpt_generations": False,
        "independent_oos_approved": False,
        "provider_pit_verified": False,
        "autonomous_gpt_evolution_effect_proven": False,
        "orders_enabled": False,
    }
    report["report_hash"] = content_hash(report)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--state", type=Path, required=True)
    ap.add_argument("--session", type=str, required=True)
    args = ap.parse_args()
    print(json.dumps(run(args.root, args.state, args.session),
                     ensure_ascii=False, indent=2, allow_nan=False))
