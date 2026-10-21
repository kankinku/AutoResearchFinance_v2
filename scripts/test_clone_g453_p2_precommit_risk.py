"""Fail-closed P2 precommit risk acceptance/rejection on cloned G452 research.

Original 452 Evidence is never mutated. Strict arm must reject real, costed
child BEFORE staging. Permissive arm runs a real G453 S2/S7 committed cycle.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash
from scripts import fresh_development_cohort_controller_20261021 as controller

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state/moon-http/fresh-20261021"
ORIGINAL = STATE / "research/academic-gpt-checkpoints"
SESSION = (STATE / "session-id.txt").read_text().strip()


def head() -> tuple[int, str]:
    with sqlite3.connect(ORIGINAL / "cycles.sqlite") as db:
        rows = db.execute(
            "SELECT generation,evidence_hash FROM generations ORDER BY generation"
        ).fetchall()
    return len(rows), content_hash(rows)


def clone_at(directory: Path, limit: ChildRiskBudget) -> AcademicMCPCheckpointService:
    target = directory / "academic-gpt-checkpoints"
    target.mkdir(parents=True)
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        with sqlite3.connect(ORIGINAL / name) as src:
            with sqlite3.connect(target / name) as dest:
                src.backup(dest)
    service = AcademicMCPCheckpointService(
        project_root=ROOT,
        state_dir=directory,
        parent_portfolio_v2=True,
        precommit_child_risk_budget=limit,
    )
    state = service.extend_completed_session(SESSION, additional_generations=1)
    assert state["completed_generations"] == 452
    assert state["requested_generations"] == 453
    assert state["checkpoint_phase"] == "AWAITING_PLAN"
    return service


def rejection_test(directory: Path) -> dict:
    service = clone_at(
        directory, ChildRiskBudget(max_child_mdd_pct=0, max_mdd_increase_pp=0, min_closed_trades=30)
    )
    start = service.get({"session_id": SESSION})
    plan = None
    for ops in controller.designs():
        proposal = {
            "mode": "structure",
            "parent_ids": [start["model_context"]["inherited_parent_strategy_id"]],
            "operations": ops,
            "rationale": "Isolated P2 risk rejection regression, all-cost S2 replay.",
        }
        try:
            service.submit_plan(
                {
                    "session_id": SESSION,
                    "checkpoint_token": start["checkpoint_token"],
                    "plan": proposal,
                    "require_execution_change": True,
                }
            )
        except ValueError as exc:
            if str(exc).startswith("P2_PRECOMMIT_RISK_REJECTED:"):
                plan = proposal
                print("REJECTED_EXPECTED", str(exc)[:200], flush=True)
                break
            continue
    assert plan is not None, "No executable candidate reached the risk gate"
    # Retrying the SAME invalid plan is reproducible and does not duplicate
    # rejection receipts or change the checkpoint token.
    try:
        service.submit_plan(
            {
                "session_id": SESSION,
                "checkpoint_token": start["checkpoint_token"],
                "plan": plan,
                "require_execution_change": True,
            }
        )
    except ValueError as exc:
        assert str(exc).startswith("P2_PRECOMMIT_RISK_REJECTED:")
    else:
        raise AssertionError("Retry bypassed risk gate")
    now = service.get({"session_id": SESSION})
    assert now["completed_generations"] == 452
    assert now["checkpoint_phase"] == "AWAITING_PLAN"
    assert now["checkpoint_token"] == start["checkpoint_token"]
    assert now["history"][-1]["evidence_hash"] == start["history"][-1]["evidence_hash"]
    with service._connect() as db:
        row = db.execute(
            "SELECT * FROM precommit_risk_rejections WHERE session_id=? AND generation=453",
            (SESSION,),
        ).fetchall()
        assert len(row) == 1
        original = json.loads(row[0]["review_json"])
        assert row[0]["review_hash"] == content_hash(original)
        assert original["risk_review"]["eligible"] is False
        assert original["child_audit_hash"] and original["child_equity_hash"]
        stage = db.execute(
            "SELECT phase,plan_json FROM stages WHERE session_id=?", (SESSION,)
        ).fetchone()
        assert stage["phase"] == "AWAITING_PLAN" and stage["plan_json"] is None
        recorded = db.execute(
            "SELECT count(*) FROM generation_timings WHERE session_id=? AND generation=453",
            (SESSION,),
        ).fetchone()[0]
        assert recorded == 0
    print("REJECTED_EVIDENCE_VERIFIED", row[0]["review_hash"], flush=True)
    return {
        "rejected_generation": 453,
        "rejection_hash": row[0]["review_hash"],
        "risk_review": original["risk_review"],
        "no_generation_committed": True,
        "token_retained": True,
        "idempotent_rejection": True,
    }


def acceptance_test(directory: Path) -> dict:
    service = clone_at(
        directory,
        ChildRiskBudget(max_child_mdd_pct=100, max_mdd_increase_pp=100, min_closed_trades=1),
    )
    proof_seen = []
    real_submit = service.submit_plan

    def captured(args):
        output = real_submit(args)
        with service._connect() as db:
            row = db.execute(
                "SELECT plan_json FROM stages WHERE session_id=?", (SESSION,)
            ).fetchone()
            plan = json.loads(row["plan_json"])
            p2 = plan["p2_precommit_approved"]
            assert p2["risk_review"]["eligible"] is True
            assert p2["review_hash"] == content_hash(
                {k: v for k, v in p2.items() if k != "review_hash"}
            )
            proof_seen.append(p2["review_hash"])
        return output

    with (
        patch.object(controller, "AcademicMCPCheckpointService", return_value=service),
        patch.object(controller, "PROGRESS", directory / "attempts.jsonl"),
        patch.object(controller, "SESSION", SESSION),
        patch.object(service, "submit_plan", side_effect=captured),
    ):
        controller.main(1)
    end = service.get({"session_id": SESSION})
    assert (end["completed_generations"], end["requested_generations"]) == (453, 453)
    assert end["checkpoint_phase"] == end["status"] == "COMPLETED"
    assert end["final_report"]["all_proposed_hypotheses_measured"] is True
    assert len(proof_seen) == 1
    with service._connect() as db:
        report = service._stored_experiment(db, SESSION, 453)
        assert report is not None
        assert report["original_generation_evidence_hash"] == end["history"][-1]["evidence_hash"]
        rejections = db.execute("SELECT count(*) FROM precommit_risk_rejections").fetchone()[0]
        assert rejections == 0
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not end["orders_enabled"] and not end["independent_oos_approved"]
    print("ACCEPTED_G453_COMMITTED", end["history"][-1]["evidence_hash"], flush=True)
    return {
        "generation": 453,
        "source_parent": end["history"][-1]["inherited_parent"]["source_generation"],
        "child_return": end["history"][-1]["metrics"]["total_return"],
        "child_mdd": end["history"][-1]["metrics"]["max_drawdown"],
        "accepted_proof_hash": proof_seen[0],
        "evidence_hash": end["history"][-1]["evidence_hash"],
        "s7_report_hash": report["record_hash"],
        "no_rejections": True,
    }


def main():
    assert head()[0] == 452
    prior = head()
    with tempfile.TemporaryDirectory(prefix="quant-p2-precommit-clone-") as tmp:
        folder = Path(tmp)
        rejected = rejection_test(folder / "strict")
        accepted = acceptance_test(folder / "permissive")
        assert head() == prior, "original G452 evidence changed"
        result = {
            "mode": "CLONED_P2_PRECOMMIT_CHILD_RISK_E2E_DEVELOPMENT_ONLY",
            "original_generation_count": prior[0],
            "original_chain_digest": prior[1],
            "original_unchanged": True,
            "strict": rejected,
            "permissive": accepted,
            "not_independent_oos": True,
            "no_broker_orders": True,
            "controller": "DETERMINISTIC_GPT_DESIGNED_POLICY_NOT_PER_GENERATION_LLM",
        }
        out = STATE / "p2-precommit-child-risk-e2e.json"
        if out.exists():
            raise RuntimeError("P2_PRECOMMIT_RESULT_EXISTS_DO_NOT_OVERWRITE")
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print("P2_PRECOMMIT_E2E_PASS", out, content_hash(result), flush=True)


if __name__ == "__main__":
    main()
