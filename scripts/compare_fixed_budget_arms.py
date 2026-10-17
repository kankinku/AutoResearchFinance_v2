"""Offline three-arm freeze/score on existing G179 evidence, not a new generation."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

from core.data.parquet import ParquetDataProvider
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from evaluation.academic_campaign_audit import _sha256, _validate_snapshot
from research.indicator_engine.algorithm_plan import AlgorithmPlan, compile_algorithm_plan
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.llm.director import ResearchIntent
from research.llm.fixed_budget_arms import (
    FixedBudgetError,
    build_fixed_budget_manifest,
    read_frozen_manifest,
    score_frozen_budget,
    write_frozen_manifest,
)
from research.llm.intent_bridge import apply_intent
from strategy_ir.schema import StrategyIR


def _sources(snapshot: Path, session: str, number: int) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_snapshot(snapshot)
    evidence = json.loads((snapshot / "risk-replay-inputs.json").read_text(encoding="utf-8"))
    if evidence["catalog_copy_sha256"] != _sha256(snapshot / "catalog-for-risk-replay.sqlite"):
        raise FixedBudgetError("copied catalog hash mismatch")
    with (
        sqlite3.connect((snapshot / "cycles.sqlite").as_uri() + "?mode=ro", uri=True) as c,
        sqlite3.connect((snapshot / "gateway.sqlite").as_uri() + "?mode=ro", uri=True) as g,
    ):
        current = c.execute(
            "SELECT evidence_json,evidence_hash FROM generations "
            "WHERE session_id=? AND generation=?",
            (session, number),
        ).fetchone()
        trial = g.execute(
            "SELECT report_json,report_hash FROM experiment_reports "
            "WHERE session_id=? AND generation=?",
            (session, number),
        ).fetchone()
    if current is None or trial is None:
        raise FixedBudgetError("missing original frozen S7 or generation")
    body, stored = json.loads(current[0]), json.loads(trial[0])
    if (
        stored["original_generation_evidence_hash"] != current[1]
        or content_hash(stored) != trial[1]
        or stored["study_scope"] != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
        or stored["report"]["causal_status"] != "NOT_ESTABLISHED"
        or stored["report"]["out_of_sample_approved"] is not False
        or stored["report"]["broker_executable"] is not False
    ):
        raise FixedBudgetError("S7 report evidence and dataset scope mismatch")
    return {**body, "evidence_hash": current[1]}, stored


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "score"))
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--market", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--generation", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20261017)
    args = parser.parse_args()
    source, s7 = _sources(args.snapshot, args.session, args.generation)
    market = ParquetDataProvider.read(args.market)
    if source["dataset_hash"] != market.dataset_hash or source.get("inherited_strategy_ir") is None:
        raise FixedBudgetError("dataset or parent inherited StrategyIR identity mismatch")
    base = compile_algorithm_plan(
        ResearchCatalog(args.snapshot / "catalog-for-risk-replay.sqlite"),
        AlgorithmPlan.model_validate(source["base_algorithm_plan"]),
        market,
    )
    ir = StrategyIR.model_validate(source["inherited_strategy_ir"])
    hash_ir = content_hash(ir.model_dump(mode="json", by_alias=True))
    if source["strategy_hash"] != hash_ir:
        raise FixedBudgetError("source StrategyIR hash mismatch")
    parent = replace(base.compiled, strategy=ir, strategy_hash=hash_ir)
    if audit_inherited_decisions(parent, market).trace_hash != source["audit_hash"]:
        raise FixedBudgetError("original source audit replay mismatch")
    gpt = [ResearchIntent.model_validate(x["proposed_intent"]) for x in source["experiments"]]
    if len(gpt) != len(s7["report"]["experiments"]):
        raise FixedBudgetError("original GPT experiments missing")
    for source_trial, intent, s7_trial in zip(
        source["experiments"], gpt, s7["report"]["experiments"], strict=True
    ):
        mutated = apply_intent(ir, intent, research_feature_specs())
        child_digest = content_hash(mutated.model_dump(mode="json", by_alias=True))
        if child_digest not in (
            source_trial["proposal_child_hash"],
            s7_trial["child_strategy_hash"],
        ):
            raise FixedBudgetError("GPT source child hash changed")
    target = args.output / "fixed-budget-frozen-plan.json"
    if args.mode == "freeze":
        plan = build_fixed_budget_manifest(
            parent, market, gpt, seed=args.seed, source_evidence_hash=source["evidence_hash"]
        )
        write_frozen_manifest(target, plan)
        print("FROZEN", plan["freeze_hash"], "K", plan["candidates_per_arm"])
        return
    plan = read_frozen_manifest(target)
    if (
        plan["source_gpt_evidence_hash"] != source["evidence_hash"]
        or plan["random_seed"] != args.seed
    ):
        raise FixedBudgetError("frozen original GPT evidence or seed changed")
    report = score_frozen_budget(parent, market, plan)
    original = s7["report"]["experiments"][0]
    gpt_measure = next(x["measured"] for x in report["trials"] if x["arm"] == "GPT_HISTORICAL")
    if (
        abs(gpt_measure["final_equity"] - original["child_final_equity"]) > 1e-6
        or abs(gpt_measure["transaction_costs"] - original["execution_delta"]["child_costs"]) > 1e-6
        or abs(report["parent"]["final_equity"] - original["parent_final_equity"]) > 1e-6
    ):
        raise FixedBudgetError("GPT historical S7 costed replay mismatch")
    with (args.output / "fixed-budget-results.json").open("x", encoding="utf-8") as out:
        json.dump(report, out, indent=2, ensure_ascii=False)
        out.write("\n")
    print("EVALUATED", report["candidate_evaluations"], "FROZEN", plan["freeze_hash"])
    for x in report["trials"]:
        m = x["measured"]
        print(
            x["arm"],
            "return",
            round(m["total_return"] * 100, 3),
            "MDD",
            round(m["max_drawdown"] * 100, 3),
            "exposure",
            round(m["market_exposure"] * 100, 3),
            "cost",
            round(m["transaction_costs"], 3),
            "closed",
            m["closed_trades"],
        )
    print("REPORT_HASH", report["report_hash"])


if __name__ == "__main__":
    run()
