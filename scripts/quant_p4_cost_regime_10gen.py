"""Read-only P4-4 stress diagnosis of the original 10 GPT-authored generations.

Usage: python scripts/quant_p4_cost_regime_10gen.py --root ROOT --state STATE --session SID
Verify source first; reconstruct its DBs only in a disposable isolated temp copy.
This does not open sealed 2026 data, mutate original results or trigger orders.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    compile_algorithm_plan,
)
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.p4_cost_regime_stress import evaluate_p4_cost_regime_stress
from scripts.quant_p4_verify_10gen import verify


def summarize(root: Path, state: Path, session_id: str) -> dict:
    source_proof = verify(root, state, session_id)
    if source_proof["independent_oos_approved"] or source_proof["orders_enabled"]:
        raise ValueError("unsafe external research proof")
    dataset = ParquetDataProvider.read(
        root / "data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet"
    )
    with TemporaryDirectory(prefix="p4-4-audit-copy-") as ephemeral:
        copied = Path(ephemeral)
        backing = state / "academic-gpt-checkpoints"
        isolated = copied / "academic-gpt-checkpoints"
        isolated.mkdir()
        for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
            with sqlite3.connect((backing / name).as_uri()+"?mode=ro", uri=True) as reader:
                with sqlite3.connect(isolated / name) as writer:
                    reader.backup(writer)
        service = AcademicMCPCheckpointService(
            project_root=root, state_dir=copied,
            parent_portfolio_v2=True, generalization_parent_v1=True,
        )
        status = service.get({"session_id": session_id})
        if (status["completed_generations"] != 10
            or len(status["history"]) != 10
            or status["independent_oos_approved"] is not False
            or status["orders_enabled"] is not False):
            raise ValueError("unverified P4-4 copied counted research history")
        catalog = service._catalog("s6-v2")
        studies = []
        for original in status["history"]:
            if original.get("inherited_strategy_ir") is not None:
                compiled = service._inherited_from_evidence(
                    catalog, dataset, original,
                    history=status["history"], session_id=session_id,
                )
                audit = audit_inherited_decisions(compiled, dataset)
            else:
                plan = AlgorithmPlan.model_validate(original["algorithm_plan"])
                plan_compiled = compile_algorithm_plan(catalog, plan, dataset)
                compiled = plan_compiled.compiled
                audit = audit_algorithm_plan(catalog, plan_compiled, dataset)
            measured = evaluate_p4_cost_regime_stress(
                compiled, audit, original, dataset,
                last_development_date=date(2025, 12, 31),
            )
            studies.append({
                "generation": original["generation"],
                "source_evidence_hash": original["evidence_hash"],
                "source_strategy_hash": original["strategy_hash"],
                "cost_stress": [asdict(s) for s in measured.scenarios],
                "calendar_years": [asdict(y) for y in measured.calendar_years],
                "regimes": [asdict(r) for r in measured.regimes],
                "stress_report_hash": measured.report_hash,
                "independent_oos_approved": False,
            })
            print("P4-4 checked G"+str(original["generation"])+
                  " baseline_return="+str(round(measured.scenarios[0].total_return*100, 3))+
                  "% all_cost_2x="+str(round(measured.scenarios[-1].total_return*100, 3))+
                  "%", file=sys.stderr, flush=True)
    after = verify(root, state, session_id)
    if after != source_proof:
        raise ValueError("P4 source state changed during supposedly read-only study")
    record = {
        "schema": "p4-4-existing-counted-development-cost-regime-v1",
        "source_report_hash": source_proof["report_hash"],
        "dataset_hash": dataset.dataset_hash,
        "period": "2020-01-02 to 2025-12-31",
        "origin": "REUSED_DEVELOPMENT_NOT_INDEPENDENT_OOS",
        "data_basis": "RAW_QQQ_NON_PIT_PRICE_ONLY",
        "model_invocation_provenance": "NOT_INDEPENDENTLY_VERIFIED",
        "regime_classifier": "PREVIOUS_63_CLOSES_AND_PREVIOUS_20_DAILY_RETURNS",
        "regime_high_vol_threshold_daily": .015,
        "sampled_strategies": len(studies),
        "studies": studies,
        "orders_enabled": False,
        "independent_oos_approved": False,
        "provider_pit_approved": False,
        "economic_p5_gate_approved": False,
    }
    record["report_hash"] = content_hash(record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--session", type=str, required=True)
    flags = parser.parse_args()
    print(json.dumps(summarize(flags.root, flags.state, flags.session),
                     ensure_ascii=False, indent=2, allow_nan=False))
