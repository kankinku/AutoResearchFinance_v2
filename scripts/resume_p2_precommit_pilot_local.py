"""Resume only the uncompleted generations of P2 realistic pilot on LOCAL SQLite.

Original isolated G452 copy is on the shared volume. The interrupted clone
is copied with SQLite backup (not raw file copying) into /tmp; both original
research and interrupted clone remain unchanged.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash
from scripts import fresh_development_cohort_controller_20261021 as controller
from scripts.run_p2_precommit_realistic_pilot import (
    DEST,
    EXPECTED_HEAD,
    ROOT,
    SID,
    N,
    original_chain,
)

BUDGET = ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=15, min_closed_trades=30)


def main() -> None:
    before = original_chain()
    local = Path(tempfile.mkdtemp(prefix="quant-p2-realistic-recover-"))
    dest = local / "academic-gpt-checkpoints"
    dest.mkdir()
    for filename in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        with sqlite3.connect(DEST / "academic-gpt-checkpoints" / filename) as source:
            with sqlite3.connect(dest / filename) as target:
                source.backup(target)
        with sqlite3.connect(dest / filename) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    shutil.copy2(DEST / "attempts.jsonl", local / "attempts.jsonl")
    service = AcademicMCPCheckpointService(
        project_root=ROOT,
        state_dir=local,
        parent_portfolio_v2=True,
        child_risk_budget=BUDGET,
        precommit_child_risk_budget=BUDGET,
    )
    before_status = service.get({"session_id": SID})
    assert before_status["completed_generations"] == 454
    assert before_status["requested_generations"] == 452 + N
    assert before_status["checkpoint_phase"] == "AWAITING_PLAN"
    remaining = before_status["requested_generations"] - before_status["completed_generations"]
    print("P2_LOCAL_RESUME", local, "remaining", remaining, "prior", 454, flush=True)
    blocked = None
    try:
        with (
            patch.object(controller, "AcademicMCPCheckpointService", return_value=service),
            patch.object(controller, "PROGRESS", local / "attempts.jsonl"),
            patch.object(controller, "SESSION", SID),
        ):
            controller.main(remaining)
    except RuntimeError as exc:
        if not str(exc).startswith("EXHAUSTED_TYPED_PLAN_POOL_G"):
            raise
        blocked = str(exc)
    final = service.get({"session_id": SID})
    with service._connect() as db:
        rejected = [
            (json.loads(r["review_json"]), r["review_hash"])
            for r in db.execute(
                "SELECT review_json,review_hash FROM precommit_risk_rejections "
                "WHERE session_id=? ORDER BY generation,rowid",
                (SID,),
            )
        ]
        assert all(content_hash(row) == digest for row, digest in rejected)
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        reports = db.execute(
            "SELECT count(*) FROM experiment_reports WHERE session_id=?", (SID,)
        ).fetchone()[0]
    assert reports == final["completed_generations"]
    new = final["history"][452:]
    assert all(r["metrics"]["max_drawdown"] * 100 <= 30 + 1e-8 for r in new)
    events = [
        json.loads(line)
        for line in (local / "attempts.jsonl").read_text().splitlines()
        if line.strip()
    ]
    details = {
        "status": "COMPLETED" if len(new) == N else "BLOCKED_STATIC_POOL",
        "blocked_reason": blocked,
        "controller": "DETERMINISTIC_SIGNED_EVIDENCE_GUIDANCE_NOT_GPT",
        "data_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_INDEPENDENT_OOS",
        "risk_budget": BUDGET.model_dump(mode="json"),
        "parent_risk_gate": True,
        "precommit_child_risk_gate": True,
        "original_chain_unchanged": original_chain() == before,
        "original_generation_count": 452,
        "clone_completed": final["completed_generations"],
        "clone_requested": final["requested_generations"],
        "actual_new_generations": len(new),
        "rejected_children": len(rejected),
        "adaptive_feedback_events": sum(
            e.get("kind") == "risk_feedback_adaptation" for e in events
        ),
        "risk_error_events": sum(
            e.get("error_type") == "P2_PRECOMMIT_RISK_REJECTED" for e in events
        ),
        "all_plan_rejections": sum(e.get("kind") == "plan_rejected" for e in events),
        "rejection_failure_modes": dict(
            Counter(
                "ABSOLUTE_MDD"
                if r["risk_review"]["child_mdd_pct"] > 30
                else "RELATIVE_MDD"
                if r["risk_review"]["child_mdd_pct"] > r["risk_review"]["parent_mdd_pct"] + 15
                else "MIN_TRADES"
                for r, _ in rejected
            )
        ),
        "mean_dev_return_pct": mean([x["metrics"]["total_return"] * 100 for x in new])
        if new
        else None,
        "mean_dev_mdd_pct": mean([x["metrics"]["max_drawdown"] * 100 for x in new])
        if new
        else None,
        "new_generations": [
            {
                "generation": x["generation"],
                "metrics": x["metrics"],
                "evidence_hash": x["evidence_hash"],
            }
            for x in new
        ],
        "full_s7_report_count": reports,
        "local_source": str(local),
        "research_orders_enabled": final["orders_enabled"],
        "independent_oos_approved": final["independent_oos_approved"],
        "checked_parent_ledger": EXPECTED_HEAD,
    }
    assert details["original_chain_unchanged"]
    assert not details["research_orders_enabled"] and not details["independent_oos_approved"]
    output = DEST / "result.json"
    if output.exists():
        raise RuntimeError("DO_NOT_OVERWRITE_PILOT_RESULT")
    output.write_text(json.dumps(details, ensure_ascii=False, indent=2) + "\n")
    print(
        "P2_LOCAL_RECOVERY_RESULT",
        json.dumps(
            {
                key: details[key]
                for key in (
                    "status",
                    "actual_new_generations",
                    "rejected_children",
                    "adaptive_feedback_events",
                    "mean_dev_return_pct",
                    "mean_dev_mdd_pct",
                    "blocked_reason",
                )
            }
        ),
        flush=True,
    )
    print("REPORT", output, content_hash(details), flush=True)


if __name__ == "__main__":
    main()
