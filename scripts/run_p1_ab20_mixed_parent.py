"""Twenty-generation A/B research study on separate cloned G452 research ledgers.

No broker, no OOS, no production mutation, no external LLM calls.
Use a separate OS process per arm to isolate patched controller globals.
Max 20 counted generations per arm; attempted candidate count measured separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from statistics import mean, median
from unittest.mock import patch

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash
from scripts import fresh_development_cohort_controller_20261021 as controller

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "state/moon-http/fresh-20261021"
ORIGINAL = SOURCE / "research/academic-gpt-checkpoints"
STUDY = SOURCE / "p1-ab20-mixed-s7-20261021"
SID = (SOURCE / "session-id.txt").read_text().strip()
EXPECTED_HEAD = "e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337"


def source_identity() -> tuple[int, str]:
    with sqlite3.connect(ORIGINAL / "cycles.sqlite") as db:
        rows = db.execute(
            "SELECT generation,evidence_hash FROM generations ORDER BY generation"
        ).fetchall()
    assert len(rows) == 452 and rows[-1] == (452, EXPECTED_HEAD)
    return len(rows), content_hash(rows)


def prepare(arm: str) -> Path:
    clone = STUDY / arm
    clone.mkdir(parents=True, exist_ok=False)
    databases = clone / "academic-gpt-checkpoints"
    databases.mkdir()
    manifest = {}
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        with sqlite3.connect(ORIGINAL / name) as src:
            with sqlite3.connect(databases / name) as dst:
                src.backup(dst)
        with sqlite3.connect(databases / name) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        manifest[name] = hashlib.sha256((databases / name).read_bytes()).hexdigest()
    (clone / "source-manifest.json").write_text(
        json.dumps({"arm": arm, "source": source_identity(), "databases": manifest}, indent=2)
        + "\n"
    )
    return clone


def audit(arm: str, svc: AcademicMCPCheckpointService) -> dict:
    report = svc.get({"session_id": SID})
    assert (report["completed_generations"], report["requested_generations"]) == (472, 472)
    assert report["status"] == report["checkpoint_phase"] == "COMPLETED"
    assert report["final_report"]["all_proposed_hypotheses_measured"] is True
    assert not report["orders_enabled"] and not report["independent_oos_approved"]
    new = report["history"][452:]
    assert len(new) == 20
    assert new[0]["previous_evidence_hash"] == EXPECTED_HEAD
    assert all(
        new[i]["previous_evidence_hash"] == new[i - 1]["evidence_hash"] for i in range(1, len(new))
    )
    with svc._connect() as db:
        for row in new:
            s7 = svc._stored_experiment(db, SID, row["generation"])
            assert s7 is not None
            assert s7["original_generation_evidence_hash"] == row["evidence_hash"]
        count = db.execute(
            "SELECT count(*) FROM experiment_reports WHERE session_id=?", (SID,)
        ).fetchone()[0]
        assert count == 472
        choices = []
        for g in range(453, 473):
            raw = db.execute(
                "SELECT selection_json FROM parent_selections "
                "WHERE session_id=? AND next_generation=?",
                (SID, g),
            ).fetchone()
            assert raw is not None
            choice = json.loads(raw[0])
            assert (
                choice["source_generation"] == new[g - 453]["inherited_parent"]["source_generation"]
            )
            choices.append(choice)
    values = [row["metrics"]["total_return"] * 100 for row in new]
    mdds = [row["metrics"]["max_drawdown"] * 100 for row in new]
    log = STUDY / arm / "attempts.jsonl"
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    data = {
        "arm": arm,
        "controller": "DETERMINISTIC_GPT_DESIGNED_POLICY_NOT_PER_GENERATION_LLM",
        "not_independent_oos": True,
        "cloned_generations": 472,
        "production_identity_unchanged": source_identity()
        == (
            452,
            content_hash(
                [(i, r["evidence_hash"]) for i, r in enumerate(report["history"][:452], start=1)]
            ),
        ),
        "first_new_generation": 453,
        "last_new_generation": 472,
        "new_generation_count": 20,
        "s7_report_count": count,
        "positive_return": sum(x > 0 for x in values),
        "mean_return_pct": mean(values),
        "median_return_pct": median(values),
        "mean_mdd_pct": mean(mdds),
        "best_new_generation": max(new, key=lambda z: z["metrics"]["total_return"])["generation"],
        "best_new_return_pct": max(values),
        "unique_parent_origins": len({c["source_generation"] for c in choices}),
        "parent_source_generations": [c["source_generation"] for c in choices],
        "parent_types": [c["source_kind"] for c in choices],
        "total_attempt_events": len(events),
        "attempt_signatures": len({e["signature"] for e in events if "signature" in e}),
        "preflight_rejections": sum(e.get("kind") == "plan_rejected" for e in events),
        "generated_generation_hashes": [z["evidence_hash"] for z in new],
        "new_generation_metrics": [{"generation": z["generation"], **z["metrics"]} for z in new],
    }
    assert data["production_identity_unchanged"]
    return data


def main(arm: str, *, resume: bool = False) -> None:
    assert arm in {"baseline", "mixed", "risk"}
    assert source_identity()[0] == 452
    clone = STUDY / arm if resume else prepare(arm)
    service = AcademicMCPCheckpointService(
        project_root=ROOT,
        state_dir=clone,
        parent_portfolio_v2=arm in ("mixed", "risk"),
        child_risk_budget=(
            ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=15, min_closed_trades=30)
            if arm == "risk"
            else None
        ),
    )
    before = service.get({"session_id": SID})
    if resume:
        assert before["requested_generations"] == 472
        assert 452 <= before["completed_generations"] < 472
        assert before["checkpoint_phase"] == "AWAITING_PLAN"
        assert not (clone / "result.json").exists()
        remaining = 472 - before["completed_generations"]
        print("ARM_RESUME", arm, before["completed_generations"], "TO_G472", flush=True)
    else:
        assert (before["completed_generations"], before["requested_generations"]) == (452, 452)
        state = service.extend_completed_session(SID, additional_generations=20)
        assert (state["completed_generations"], state["requested_generations"]) == (452, 472)
        remaining = 20
        print("ARM_STARTED", arm, "G452_TO_G472", flush=True)
    with (
        patch.object(controller, "AcademicMCPCheckpointService", return_value=service),
        patch.object(controller, "PROGRESS", clone / "attempts.jsonl"),
        patch.object(controller, "SESSION", SID),
    ):
        controller.main(remaining)
    report = audit(arm, service)
    output = clone / "result.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        "ARM_COMPLETED",
        arm,
        json.dumps(
            {
                "count": report["new_generation_count"],
                "mean_return_pct": round(report["mean_return_pct"], 3),
                "mean_mdd_pct": round(report["mean_mdd_pct"], 3),
                "parents": report["unique_parent_origins"],
                "attempts": report["attempt_signatures"],
            }
        ),
        "RESULT",
        output,
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("baseline", "mixed", "risk"), required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    main(args.arm, resume=args.resume)
