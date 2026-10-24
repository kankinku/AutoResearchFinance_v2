"""Read-only independent workspace audit of a 10-generation P4 GPT checkpoint study.

Example:
  python scripts/quant_p4_verify_10gen.py \
    --root /shared/moon-workspace/AutoResearchFinance_v2-fresh-research-20261021 \
    --state /shared/moon-workspace/AutoResearchFinance_v2-p4-rehearsal-20261024 \
    --session 2d86df1adb5945259c1b95e394d6a78a

Does not enable orders, change any OAuth configuration, or access 2026 data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Permit direct execution from the repository root without PYTHONPATH setup.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash
from research.indicator_engine.development_benchmark import (
    compare_qqq_development_benchmarks,
)


def verify(root: Path, state: Path, session_id: str) -> dict[str, Any]:
    root, state = root.resolve(), state.resolve()
    if state.is_relative_to(root) or not state.is_dir():
        raise ValueError("P4 verification must use an independent existing state directory")
    service = AcademicMCPCheckpointService(
        project_root=root,
        state_dir=state,
        parent_portfolio_v2=True,
        generalization_parent_v1=True,
    )
    result = service.get({"session_id": session_id})
    if not (
        result["completed_generations"] == 10
        and result["requested_generations"] == 10
        and result["status"] == "COMPLETED"
        and result["checkpoint_phase"] == "COMPLETED"
        and result["orders_enabled"] is False
        and result["independent_oos_approved"] is False
    ):
        raise ValueError("P4 session is incomplete or has unsafe permissions")
    history = result["history"]
    if (
        len(history) != 10
        or [x["generation"] for x in history] != list(range(1, 11))
        or len({x["strategy_hash"] for x in history}) != 10
        or any(
            x.get("broker_executable") is not False
            or x.get("independent_oos_approved") is not False
            for x in history
        )
    ):
        raise ValueError("P4 counted generations have incomplete identity or unsafe claims")
    dataset = ParquetDataProvider.read(
        root / "data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet"
    )
    if dataset.bars[-1].timestamp.year != 2025:
        raise ValueError("incorrect development data upper bound")
    if any(x["dataset_hash"] != dataset.dataset_hash for x in history):
        raise ValueError("counted development dataset mutated")
    benchmark = compare_qqq_development_benchmarks(
        dataset,
    )["qqq_costed_buy_and_hold"]["total_return"]
    s7_status = []
    parent_proofs = []
    with service._connect() as conn:
        enrollment = conn.execute(
            "SELECT dataset_hash,policy FROM generalization_enrollments WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if (
            enrollment is None
            or enrollment["dataset_hash"] != dataset.dataset_hash
            or enrollment["policy"] != "AUDITED_EX_POST_PARENT_V1"
        ):
            raise ValueError("P3-B original research registration invalid")
        for x in history:
            gen = x["generation"]
            rec = service._stored_experiment(conn, session_id, gen)
            if (
                rec is None
                or rec["original_generation_evidence_hash"] != x["evidence_hash"]
                or len(rec["report"]["experiments"]) != 1
                or rec["report"]["experiments"][0].get("status") is None
            ):
                raise ValueError(f"generation {gen} missing verified paired S7")
            s7_status.append(rec["report"]["experiments"][0]["status"])
            if x.get("inherited_strategy_ir"):
                row = conn.execute(
                    "SELECT selection_json,selection_hash FROM parent_selections "
                    "WHERE session_id=? AND next_generation=?",
                    (session_id, gen),
                ).fetchone()
                if row is None:
                    raise ValueError(f"inherited generation {gen} missing pinned parent")
                selected = json.loads(row["selection_json"])
                if (
                    selected["selection_hash"] != row["selection_hash"]
                    or content_hash({
                        k: v for k, v in selected.items() if k != "selection_hash"
                    }) != row["selection_hash"]
                    or selected["selection_basis"]
                    != "P3_AUDITED_EX_POST_GENERALIZATION_OPT_IN"
                    or selected["generalization_receipt"]["independent_oos_approved"] is not False
                ):
                    raise ValueError(f"inherited generation {gen} parent selection invalid")
                parent_proofs.append({
                    "generation": gen,
                    "parent_kind": selected["source_kind"],
                    "source_generation": selected["source_generation"],
                    "selection_hash": selected["selection_hash"],
                    "study_receipt_hash": selected["generalization_receipt"]["preview_hash"],
                })
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("gateway SQLite integrity failed")
        if conn.execute(
            "SELECT COUNT(*) FROM experiment_reports WHERE session_id=?", (session_id,)
        ).fetchone()[0] != 10:
            raise ValueError("P4 S7 report count not exactly ten")
        if conn.execute(
            "SELECT COUNT(*) FROM parent_selections WHERE session_id=?", (session_id,)
        ).fetchone()[0] != 2:
            raise ValueError("P4 selection pin count not exactly two")
    with sqlite3.connect(
        (state / "academic-gpt-checkpoints" / "cycles.sqlite").as_uri() + "?mode=ro",
        uri=True,
    ) as conn:
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("cycles SQLite integrity failed")
        if conn.execute(
            "SELECT COUNT(*) FROM generations WHERE session_id=?", (session_id,)
        ).fetchone()[0] != 10:
            raise ValueError("P4 counted ledger is not exactly ten generations")
    reports = [
        {
            "generation": x["generation"],
            "total_return_pct": round(100 * x["metrics"]["total_return"], 5),
            "mdd_pct": round(100 * x["metrics"]["max_drawdown"], 5),
            "trades_closed": x["metrics"]["trade_count"],
            "exposure_pct": round(100 * x["metrics"]["exposure"], 5),
            "strategy_hash": x["strategy_hash"],
            "evidence_hash": x["evidence_hash"],
            "inherited": bool(x.get("inherited_strategy_ir")),
        }
        for x in history
    ]
    db_sha = {
        name: hashlib.sha256(
            (state / "academic-gpt-checkpoints" / name).read_bytes()
        ).hexdigest()
        for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite")
    }
    record = {
        "schema": "quant-p4-ten-counted-develop-only-v1",
        "session_id": session_id,
        "status": "TECHNICAL_INTEGRATION_VERIFIED_ECONOMIC_GOAL_NOT_MET",
        "model_decision_origin": (
            "GPT_AUTHORED_CHAT_TOOL_SUBMISSIONS_NO_INDEPENDENT_MODEL_CALL_RECEIPTS"
        ),
        "dataset_hash": dataset.dataset_hash,
        "qqq_costed_buy_and_hold_return_pct": round(100 * benchmark, 5),
        "qqq_outperformance_generations": sum(
            row["metrics"]["total_return"] > benchmark for row in history
        ),
        "measured_generations": reports,
        "s7_result_counts": dict(sorted(Counter(s7_status).items())),
        "verified_parent_selections": parent_proofs,
        "source_state_sha256": db_sha,
        "orders_enabled": False,
        "independent_oos_approved": False,
        "research_ready_for_100": False,
    }
    record["report_hash"] = content_hash(record)
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--session", type=str, required=True)
    args = p.parse_args()
    print(json.dumps(
        verify(args.root, args.state, args.session),
        indent=2, ensure_ascii=False, allow_nan=False,
    ))
