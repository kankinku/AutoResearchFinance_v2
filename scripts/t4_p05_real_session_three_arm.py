"""Read-only G25 53-generation source → frozen 5×3 controlled development study.

The five authored probes below were fixed before *any* outcomes from this study
were measured. This is NOT authenticated GPT model provenance or a blind/OOS run.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from core.data.contracts import MarketDataSet
from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    compile_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy
from research.llm.director import ResearchIntent
from research.llm.fixed_budget_arms import (
    FixedBudgetError,
    build_fixed_budget_manifest,
    read_frozen_manifest,
    score_frozen_budget,
    write_frozen_manifest,
)

SID = "c1eadd67bad94d7ea182dc274224dbce"
G = 25
SEED = 20261019
ORIGIN = "DECLARED_CHATGPT_CLIENT_UNVERIFIED"
SOURCE = Path("/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory")
DB = SOURCE / "state/moon-http/research/academic-gpt-checkpoints"
MARKET = SOURCE / "data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet"

# Deliberately only one typed scalar decision-coordinate change per slot,
# comparable to existing fixed-budget_arms' random/local one-coordinate policy.
# The original parent has -3.37% net return, 6.56% MDD, 59 completed trades,
# and ~6.96% market exposure. It under-participated. Earlier S7 stricter
# confidence cut turnover and improved development return, but is known on
# reused data. Our probes test both directions and may fail.
FROZEN_PROBES = (
    (
        "entry.conditions.0",
        "greater_than",
        0.62,
        (
            "G25 rarely participated (about 7 percent exposure); admit moderate "
            "confirmation to test missed recoveries versus false entries."
        ),
    ),
    (
        "entry.conditions.0",
        "greater_than",
        0.82,
        (
            "G25 lost money despite 59 completed trades; demand stronger votes "
            "to test false positives even if opportunity is lost."
        ),
    ),
    (
        "exit.conditions.0",
        "less_equal",
        0.54,
        (
            "Replace binary exit with vote-confidence 0.54 to test whether "
            "declining EMA consensus exits before observed reversals."
        ),
    ),
    (
        "exit.conditions.0",
        "less_equal",
        0.70,
        (
            "Exit earlier as measured consensus weakens; compare avoided "
            "drawdown with turnover and fees on the same tape."
        ),
    ),
    (
        "exit.conditions.0",
        "less_equal",
        0.82,
        (
            "A defensive 0.82 exit may eliminate weak-vote exposure; "
            "alternative is losing trend capture and worse net return."
        ),
    ),
)


def _source() -> tuple[dict[str, Any], dict[str, Any]]:
    with sqlite3.connect(f"file:{DB / 'cycles.sqlite'}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            (
                "SELECT evidence_json,evidence_hash FROM generations "
                "WHERE session_id=? AND generation=?"
            ),
            (SID, G),
        ).fetchone()
        if row is None:
            raise FixedBudgetError("canonical G25 research evidence missing")
        source = json.loads(row["evidence_json"])
        source["evidence_hash"] = row["evidence_hash"]
        status = db.execute("SELECT completed FROM sessions WHERE id=?", (SID,)).fetchone()[0]
        if status != 53:
            raise FixedBudgetError("canonical study no longer at immutable 53 generation baseline")
    with sqlite3.connect(f"file:{DB / 'gateway.sqlite'}?mode=ro", uri=True) as db:
        row = db.execute(
            (
                "SELECT report_json,report_hash FROM experiment_reports "
                "WHERE session_id=? AND generation=?"
            ),
            (SID, G),
        ).fetchone()
        if row is None or content_hash(json.loads(row[0])) != row[1]:
            raise FixedBudgetError("original S7 report missing or altered")
        s7 = json.loads(row[0])
        if s7["original_generation_evidence_hash"] != source["evidence_hash"]:
            raise FixedBudgetError("G25 evidence and S7 mismatch")
    return source, s7


def _parent_and_market(
    source: dict[str, Any], scratch: Path
) -> tuple[CompiledAcademicStrategy, MarketDataSet]:
    if not MARKET.is_file():
        raise FixedBudgetError("original QQQ market parquet missing")
    market = ParquetDataProvider.read(MARKET)
    if market.dataset_hash != source["dataset_hash"]:
        raise FixedBudgetError("original QQQ dataset changed")
    # ResearchCatalog has an initializing constructor; only give it an online
    # SQLite backup in a private temporary directory, NEVER the live catalog.
    with (
        sqlite3.connect(f"file:{DB / 'catalog-s6-v2.sqlite'}?mode=ro", uri=True) as original,
        sqlite3.connect(scratch / "catalog.sqlite") as copied,
    ):
        original.backup(copied)
    compiled = compile_algorithm_plan(
        ResearchCatalog(scratch / "catalog.sqlite"),
        AlgorithmPlan.model_validate(source["algorithm_plan"]),
        market,
    )
    if (
        compiled.compiled.strategy_hash != source["strategy_hash"]
        or audit_algorithm_plan(
            ResearchCatalog(scratch / "catalog.sqlite"), compiled, market
        ).trace_hash
        != source["audit_hash"]
    ):
        raise FixedBudgetError("G25 canonical strategy hash or costed audit mismatch")
    return compiled.compiled, market


def _proposals(parent: CompiledAcademicStrategy) -> list[ResearchIntent]:
    proposals = []
    for i, (path, op, value, reason) in enumerate(FROZEN_PROBES, 1):
        proposals.append(
            ResearchIntent.model_validate(
                {
                    "mode": "structure",
                    "parent_ids": [parent.strategy.strategy_id],
                    "operations": [
                        {
                            "op": "REPLACE_RULE",
                            "path": path,
                            "condition": {"op": op, "left": "plan_vote_score", "value": value},
                        }
                    ],
                    "rationale": f"PREREGISTERED_P0_5_G25_SLOT_{i}: {reason}",
                }
            )
        )
    return proposals


def run() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=["freeze", "score"])
    cli.add_argument("--output", required=True, type=Path)
    cli.add_argument(
        "--control-policy",
        choices=(
            "RANDOM_UNIFORM_LOCAL_5PCT_RANGE_V1",
            "PLAN_VOTE_SCORE_MATCHED_COORDINATES_V2",
        ),
        default="RANDOM_UNIFORM_LOCAL_5PCT_RANGE_V1",
    )
    a = cli.parse_args()
    evidence, _s7 = _source()
    with TemporaryDirectory(prefix="t4-p05-catalog-copy-") as tmp:
        parent, market = _parent_and_market(evidence, Path(tmp))
        path = a.output / "fixed-budget-frozen-plan.json"
        if a.mode == "freeze":
            proposal = _proposals(parent)
            plan = build_fixed_budget_manifest(
                parent,
                market,
                proposal,
                seed=SEED,
                source_evidence_hash=evidence["evidence_hash"],
                research_origin=ORIGIN,
                control_policy=a.control_policy,
            )
            a.output.mkdir(parents=True, exist_ok=True)
            write_frozen_manifest(path, plan)
            print(
                json.dumps(
                    {
                        "stage": "FROZEN_ONLY_NO_EVALUATIONS",
                        "manifest_hash": plan["freeze_hash"],
                        "arm_budget": plan["candidates_per_arm"],
                        "source_hash": evidence["evidence_hash"],
                        "origin": ORIGIN,
                    },
                    indent=2,
                )
            )
            return
        plan = read_frozen_manifest(path)
        if (
            plan["source_gpt_evidence_hash"] != evidence["evidence_hash"]
            or plan["random_seed"] != SEED
            or plan["research_origin"] != ORIGIN
            or plan["policy_version"] != a.control_policy
        ):
            raise FixedBudgetError("frozen original provenance mismatch")
        report = score_frozen_budget(parent, market, plan)
        destination = a.output / "fixed-budget-results.json"
        with destination.open("x", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        print(
            json.dumps(
                {
                    "stage": "SCORED_READ_ONLY",
                    "freeze_hash": plan["freeze_hash"],
                    "result_hash": report["report_hash"],
                    "parent": report["parent"],
                    "arms": report["arms"],
                    "qqq": report["benchmark"],
                    "candidate_evaluations": report["candidate_evaluations"],
                    "duplicate_hash_count": report["cross_arm_duplicate_candidate_hashes"],
                    "model_authenticity": report["model_identity_verified"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    run()
