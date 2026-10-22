"""Opt-in P3 semantic retry on an isolated 452-generation academic SQLite clone.

This script uses explicit deterministic fixture proposals to verify two
pre-backtest semantic rejection modes and a valid counted G453 plus S7.
It does NOT claim real autonomous LLM generation or independent OOS.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash
from scripts import fresh_development_cohort_controller_20261021 as scripted
from scripts.test_clone_g453_p2_precommit_risk import head

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state/moon-http/fresh-20261021"
SOURCE = STATE / "research/academic-gpt-checkpoints"
SID = (STATE / "session-id.txt").read_text().strip()


def intent(parent_id: str, alias: str, threshold: float) -> dict:
    return {
        "mode": "structure",
        "parent_ids": [parent_id],
        "operations": [
            {
                "op": "ADD_RULE",
                "path": "exit.conditions",
                "condition": {"op": "less_equal", "left": alias, "value": threshold},
            }
        ],
        "rationale": "Verify semantic nonredundancy without a full child backtest.",
    }


def main():
    original = head()
    assert original[0] == 452
    with tempfile.TemporaryDirectory(prefix="p3-semantic-clone-") as temp:
        target = Path(temp) / "academic-gpt-checkpoints"
        target.mkdir()
        for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
            with sqlite3.connect(SOURCE / name) as src:
                with sqlite3.connect(target / name) as dst:
                    src.backup(dst)
        budget = ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=15, min_closed_trades=30)
        service = AcademicMCPCheckpointService(
            project_root=ROOT,
            state_dir=Path(temp),
            parent_portfolio_v2=True,
            child_risk_budget=budget,
            precommit_child_risk_budget=budget,
            p3_semantic_preflight=True,
        )
        begun = service.extend_completed_session(SID, additional_generations=1)
        assert begun["checkpoint_phase"] == "AWAITING_PLAN"
        parent_id = begun["model_context"]["inherited_parent_strategy_id"]
        assert begun["model_context"]["selected_development_parent"]["source_generation"] == 68
        token = begun["checkpoint_token"]
        attempts = [
            (
                "symbolic",
                intent(parent_id, "ema_direction_20", 0.25),
                "PROVABLE_CONDITION_SUBSUMPTION",
            ),
            (
                "observational",
                intent(parent_id, "ema_direction_20", 0.75),
                "DEVELOPMENT_SIGNAL_EQUIVALENCE",
            ),
        ]
        for label, plan, expected in attempts:
            try:
                service.submit_plan(
                    {
                        "session_id": SID,
                        "checkpoint_token": token,
                        "plan": plan,
                        "require_execution_change": True,
                    }
                )
            except ValueError as exc:
                assert str(exc).startswith("P3_SEMANTIC_PREFLIGHT_REJECTED:")
                assert expected in str(exc)
            else:
                raise AssertionError(f"semantic gate failed: {label}")
            now = service.get({"session_id": SID})
            assert (now["completed_generations"], now["checkpoint_phase"]) == (452, "AWAITING_PLAN")
            assert now["checkpoint_token"] == token
            assert now["model_context"]["p3_semantic_rejection_feedback"]["rejection_count"] == (
                1 if label == "symbolic" else 2
            )
        with service._connect() as db:
            records = db.execute(
                "SELECT review_json,review_hash FROM p3_semantic_rejections "
                "WHERE session_id=? AND generation=453 ORDER BY rowid",
                (SID,),
            ).fetchall()
            assert len(records) == 2
            for r in records:
                assert content_hash(json.loads(r["review_json"])) == r["review_hash"]
            assert (
                db.execute(
                    "SELECT count(*) FROM generation_timings WHERE generation=453"
                ).fetchone()[0]
                == 0
            )

        # Same redundant hypothesis resent: exactly one persisted record each.
        for _, plan, _ in attempts:
            try:
                service.submit_plan(
                    {
                        "session_id": SID,
                        "checkpoint_token": token,
                        "plan": plan,
                        "require_execution_change": True,
                    }
                )
            except ValueError as exc:
                assert "P3_SEMANTIC_PREFLIGHT_REJECTED" in str(exc)
            else:
                raise AssertionError("idempotent semantic rejection bypassed")
        with service._connect() as db:
            assert db.execute("SELECT count(*) FROM p3_semantic_rejections").fetchone()[0] == 2
        valid = intent(parent_id, "plan_vote_score", 0.5)
        staged = service.submit_plan(
            {
                "session_id": SID,
                "checkpoint_token": token,
                "plan": valid,
                "require_execution_change": True,
            }
        )
        assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
        diagnosis = scripted.diagnosis(
            staged["model_context"],
            generation=453,
            parent={},
            applied_ops=valid["operations"],
        )
        # P3 next_intent gate: reject an already-subsumed OR-exit before G453.
        redundant = json.loads(json.dumps(diagnosis))
        redundant["hypotheses"][0]["next_intent"]["operations"] = [
            {
                "op": "ADD_RULE", "path": "exit.conditions",
                "condition": {"op": "less_equal", "left": "ema_direction_20", "value": 0.25},
            }
        ]
        diagnosis_token = staged["checkpoint_token"]
        for _ in range(2):
            try:
                service.submit_diagnosis({
                    "session_id": SID, "checkpoint_token": diagnosis_token,
                    "diagnosis": redundant, "require_signal_change": True,
                })
            except ValueError as exc:
                assert str(exc).startswith("P3_DIAGNOSIS_SEMANTIC_REJECTED:")
            else:
                raise AssertionError("redundant next_intent reached counted commit")
            waiting = service.get({"session_id": SID})
            assert waiting["completed_generations"] == 452
            assert waiting["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
            assert waiting["checkpoint_token"] == diagnosis_token
            feedback = waiting["model_context"]["p3_diagnostic_semantic_feedback"]
            assert feedback["rejection_count"] == 1
            assert feedback["recent_rejections"][0]["rejected_hypothesis_ids"]
        with service._connect() as db:
            rejected_rows = db.execute(
                "SELECT review_json,review_hash FROM p3_diagnostic_semantic_rejections "
                "WHERE session_id=? AND generation=?", (SID, 453)
            ).fetchall()
            assert len(rejected_rows) == 1
            assert content_hash(json.loads(rejected_rows[0]["review_json"])) == (
                rejected_rows[0]["review_hash"]
            )
        # Tampering with stored semantic feedback must fail closed.
        with service._connect() as db:
            db.execute(
                "UPDATE p3_diagnostic_semantic_rejections SET review_hash=? "
                "WHERE session_id=? AND generation=?",
                ("0" * 64, SID, 453),
            )
        from research.llm.autonomous_cycle import CycleStateError
        try:
            service.get({"session_id": SID})
        except CycleStateError as exc:
            assert "P3 diagnostic rejection proof invalid" in str(exc)
        else:
            raise AssertionError("tampered diagnostic rejection receipt accepted")
        with service._connect() as db:
            db.execute(
                "UPDATE p3_diagnostic_semantic_rejections SET review_hash=? "
                "WHERE session_id=? AND generation=?",
                (rejected_rows[0]["review_hash"], SID, 453),
            )
        committed = service.submit_diagnosis(
            {
                "session_id": SID,
                "checkpoint_token": staged["checkpoint_token"],
                "diagnosis": diagnosis,
                "require_signal_change": True,
            }
        )
        assert (committed["completed_generations"], committed["checkpoint_phase"]) == (
            453,
            "COMPLETED",
        )
        s7 = service.evaluate_experiments({"session_id": SID, "generation": 453})
        assert s7["original_generation_evidence_hash"] == committed["history"][-1]["evidence_hash"]
        with service._connect() as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert head() == original
        print(
            "P3_SEMANTIC_CLONE_PASS",
            json.dumps(
                {
                    "symbolic_rejections": 1,
                    "development_signal_equivalence_rejections": 1,
                    "stored_rejections": len(records),
                    "diagnostic_next_intent_rejections": len(rejected_rows),
                    "valid_child_generation": 453,
                    "child_dev_return": committed["history"][-1]["metrics"]["total_return"],
                    "child_dev_mdd": committed["history"][-1]["metrics"]["max_drawdown"],
                    "s7_report_hash": s7["record_hash"],
                    "original_g452_unchanged": True,
                    "real_model_api_invocations": 0,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
