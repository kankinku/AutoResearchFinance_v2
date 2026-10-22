"""P3 provider-injected E2E on a copied G452 session. NO REAL GPT call.

Use an already measured control proposal to validate transport -> P2/S2 ->
counted generation -> diagnosis -> S7; this cannot demonstrate discovery.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget
from core.integrity.hashes import content_hash
from research.llm.inherited_checkpoint_autopilot import (
    ModelProposalAudit,
    P3InheritedCheckpointAutopilot,
)
from scripts import fresh_development_cohort_controller_20261021 as scripted
from scripts.test_clone_g453_p2_precommit_risk import head

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "state/moon-http/fresh-20261021"
ORIGINAL = SOURCE / "research/academic-gpt-checkpoints"
SID = (SOURCE / "session-id.txt").read_text().strip()
OP = [{"op": "CHANGE_AND_OR", "path": "entry.logic", "logic": "OR"}]


class HistoricalScriptedProvider:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, context: dict) -> dict:
        self.calls += 1
        if context.get("output_contract") == "InheritedResearchIntent":
            return {
                "mode": "structure",
                "parent_ids": [context["inherited_parent_strategy_id"]],
                "operations": OP,
                "rationale": (
                    "Previously measured G453 rule change for a P3 connection test, "
                    "not model discovery."
                ),
            }
        if context.get("schema") == "research-diagnostic-context-v1":
            return scripted.diagnosis(
                context,
                generation=453,
                parent={},
                applied_ops=OP,
            )
        raise RuntimeError("UNSUPPORTED_SCRIPTED_CONTEXT")


def main() -> None:
    original = head()
    assert original[0] == 452
    with tempfile.TemporaryDirectory(prefix="quant-p3-clone-") as temp:
        base = Path(temp)
        target = base / "academic-gpt-checkpoints"
        target.mkdir()
        for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
            with sqlite3.connect(ORIGINAL / name) as src:
                with sqlite3.connect(target / name) as dst:
                    src.backup(dst)
        svc = AcademicMCPCheckpointService(
            project_root=ROOT,
            state_dir=base,
            parent_portfolio_v2=True,
            child_risk_budget=ChildRiskBudget(
                max_child_mdd_pct=30,
                max_mdd_increase_pp=15,
                min_closed_trades=30,
            ),
            precommit_child_risk_budget=ChildRiskBudget(
                max_child_mdd_pct=30,
                max_mdd_increase_pp=15,
                min_closed_trades=30,
            ),
        )
        extended = svc.extend_completed_session(SID, additional_generations=1)
        assert extended["checkpoint_phase"] == "AWAITING_PLAN"
        provider = HistoricalScriptedProvider()
        receipts = base / "p3-model-receipts.jsonl"
        proof = P3InheritedCheckpointAutopilot(
            svc,
            provider,
            receipts=ModelProposalAudit(receipts, session_id=SID),
            max_plan_attempts=2,
        ).run(SID, max_generations=1)
        final = svc.get({"session_id": SID})
        assert final["completed_generations"] == final["requested_generations"] == 453
        assert proof["new_generations"] == 1 and proof["planning_proposals"] == 1
        assert provider.calls == 2
        assert (
            final["history"][-1]["previous_evidence_hash"]
            == extended["history"][-1]["evidence_hash"]
        )
        assert final["history"][-1]["metrics"]["max_drawdown"] <= 0.3
        with svc._connect() as db:
            s7 = svc._stored_experiment(db, SID, 453)
            assert s7["original_generation_evidence_hash"] == final["history"][-1]["evidence_hash"]
            assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
        rows = [json.loads(line) for line in receipts.read_text().splitlines()]
        assert len(rows) == 2
        previous = None
        for row in rows:
            assert row["previous_receipt_hash"] == previous
            assert row["receipt_hash"] == content_hash(
                {k: v for k, v in row.items() if k != "receipt_hash"}
            )
            previous = row["receipt_hash"]
        assert previous == proof["receipt_head_hash"]
        assert original == head(), "Original G452 lineage unexpectedly mutated"
        print(
            "P3_CLONE_E2E_PASS",
            json.dumps(
                {
                    "generation": 453,
                    "model_calls": "NONE: scripted provider only",
                    "mocked_proposal_count": provider.calls,
                    "child_return": final["history"][-1]["metrics"]["total_return"],
                    "child_mdd": final["history"][-1]["metrics"]["max_drawdown"],
                    "s7_report_hash": s7["record_hash"],
                    "child_evidence_hash": final["history"][-1]["evidence_hash"],
                    "receipts_hash": proof["receipt_head_hash"],
                    "production_unchanged": True,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
