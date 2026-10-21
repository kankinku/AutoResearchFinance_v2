"""Bounded, one-shot P2 realistic risk-cap pilot on a cloned G452 ledger.

Maximum 5 counted generations, same 2020-2025 non-PIT development data.
Failing to find a compliant child is a legitimate BLOCKED result, not a reason
to reduce the declared 30% MDD / +15pp / 30-trade gates.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash
from scripts import fresh_development_cohort_controller_20261021 as controller

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "state/moon-http/fresh-20261021"
DBS = SOURCE / "research/academic-gpt-checkpoints"
DEST = SOURCE / "p2-precommit-realistic-5gen-20261021"
SID = (SOURCE / "session-id.txt").read_text().strip()
EXPECTED_HEAD = "e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337"
BUDGET = ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=15, min_closed_trades=30)
N = 5


def original_chain() -> tuple[int, str]:
    with sqlite3.connect(DBS / "cycles.sqlite") as db:
        rows = db.execute(
            "SELECT generation,evidence_hash FROM generations ORDER BY generation"
        ).fetchall()
    assert len(rows) == 452 and rows[-1] == (452, EXPECTED_HEAD)
    return len(rows), content_hash(rows)


def main() -> None:
    before = original_chain()
    DEST.mkdir(parents=True, exist_ok=False)
    destination = DEST / "academic-gpt-checkpoints"
    destination.mkdir()
    checksums: dict[str, str] = {}
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        with sqlite3.connect(DBS / name) as src:
            with sqlite3.connect(destination / name) as target:
                src.backup(target)
        with sqlite3.connect(destination / name) as check:
            assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        checksums[name] = hashlib.sha256((destination / name).read_bytes()).hexdigest()
    service = AcademicMCPCheckpointService(
        project_root=ROOT,
        state_dir=DEST,
        parent_portfolio_v2=True,
        child_risk_budget=BUDGET,
        precommit_child_risk_budget=BUDGET,
    )
    status = service.extend_completed_session(SID, additional_generations=N)
    assert (status["completed_generations"], status["requested_generations"]) == (452, 457)
    print("P2_REALISTIC_PILOT_STARTED", BUDGET.model_dump(mode="json"), flush=True)
    failure = None
    try:
        with (
            patch.object(controller, "AcademicMCPCheckpointService", return_value=service),
            patch.object(controller, "PROGRESS", DEST / "attempts.jsonl"),
            patch.object(controller, "SESSION", SID),
        ):
            controller.main(N)
    except RuntimeError as exc:
        if not str(exc).startswith("EXHAUSTED_TYPED_PLAN_POOL_G"):
            raise
        failure = str(exc)
    end = service.get({"session_id": SID})
    with service._connect() as db:
        rejections = [
            (json.loads(row["review_json"]), row["review_hash"])
            for row in db.execute(
                "SELECT review_json,review_hash FROM precommit_risk_rejections "
                "WHERE session_id=? ORDER BY generation,rowid",
                (SID,),
            )
        ]
        assert all(content_hash(row) == digest for row, digest in rejections)
        counts = db.execute(
            "SELECT count(*) FROM experiment_reports WHERE session_id=?", (SID,)
        ).fetchone()[0]
        assert counts == end["completed_generations"]
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    new = end["history"][452:]
    assert len(new) <= N
    assert all(
        new[i]["previous_evidence_hash"]
        == (EXPECTED_HEAD if i == 0 else new[i - 1]["evidence_hash"])
        for i in range(len(new))
    )
    assert all(m["metrics"]["max_drawdown"] * 100 <= BUDGET.max_child_mdd_pct + 1e-8 for m in new)
    events = [
        json.loads(line)
        for line in (DEST / "attempts.jsonl").read_text().splitlines()
        if line.strip()
    ]
    adapted = [e for e in events if e.get("kind") == "risk_feedback_adaptation"]
    risk_rejected_events = [
        e for e in events if e.get("error_type") == "P2_PRECOMMIT_RISK_REJECTED"
    ]
    decision = {
        "schema": "p2-realistic-budget-pilot-v1",
        "status": "COMPLETED" if len(new) == N else "BLOCKED_BY_STATIC_POLICY",
        "failure": failure,
        "original_unchanged": original_chain() == before,
        "original_chain_digest": before[1],
        "data_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_INDEPENDENT_OOS",
        "controller": "DETERMINISTIC_SIGNED_EVIDENCE_GUIDANCE_NOT_GPT",
        "requested_new_generations": N,
        "actual_new_generations": len(new),
        "total_completed_in_clone": end["completed_generations"],
        "child_max_mdd_pct": BUDGET.max_child_mdd_pct,
        "max_child_parent_mdd_delta_pp": BUDGET.max_mdd_increase_pp,
        "min_closed_trades": BUDGET.min_closed_trades,
        "rejected_child_count": len(rejections),
        "risk_rejected_event_count": len(risk_rejected_events),
        "risk_feedback_adaptations": len(adapted),
        "observed_failure_modes": dict(
            Counter(
                "ABSOLUTE_MDD"
                if item["risk_review"]["child_mdd_pct"] > 30
                else "RELATIVE_MDD"
                if item["risk_review"]["child_mdd_pct"] > item["risk_review"]["parent_mdd_pct"] + 15
                else "INSUFFICIENT_TRADES"
                for item, _ in rejections
            )
        ),
        "mean_new_return_pct": mean([x["metrics"]["total_return"] * 100 for x in new])
        if new
        else None,
        "mean_new_mdd_pct": mean([x["metrics"]["max_drawdown"] * 100 for x in new])
        if new
        else None,
        "last_evidence_hash": new[-1]["evidence_hash"] if new else EXPECTED_HEAD,
        "source_snapshot_sha256": checksums,
        "new_metrics": [{"generation": x["generation"], **x["metrics"]} for x in new],
        "immutable_report_count_in_clone": counts,
        "orders_enabled": end["orders_enabled"],
        "independent_oos_approved": end["independent_oos_approved"],
    }
    assert decision["original_unchanged"]
    assert decision["orders_enabled"] is False
    assert decision["independent_oos_approved"] is False
    out = DEST / "result.json"
    out.write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n")
    print(
        "P2_REALISTIC_PILOT_RESULT",
        json.dumps(
            {
                "status": decision["status"],
                "new_generations": decision["actual_new_generations"],
                "rejections": decision["rejected_child_count"],
                "adaptations": decision["risk_feedback_adaptations"],
                "mean_return": decision["mean_new_return_pct"],
                "mean_mdd": decision["mean_new_mdd_pct"],
                "failure": failure,
            }
        ),
        flush=True,
    )
    print("AUDIT_JSON", out, content_hash(decision), flush=True)


if __name__ == "__main__":
    main()
