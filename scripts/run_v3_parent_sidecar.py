"""Resume-safe V3 *development* candidate decisions from actual G452 evidence.

Runs the costed S2 and P2 again, cross-checks the immutable saved 6-way report,
and appends only to a new isolated SQLite sidecar. Never counts GPT generations.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget, assess_child_risk
from core.integrity.hashes import content_hash
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.llm.composite_crossover_v3 import compose
from research.llm.ledger_donors_v3 import checkout_counted_donors
from research.llm.v3_parent_sidecar import ResearchParentSidecar

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "state/moon-http/fresh-20261021"
INPUT = (
    ROOT
    / "state/moon-http/quant-moon-bounded-100-20261023"
    / "v3-ledger-donor-checkout-dedup-20261023.json"
)
S7_INPUT = (
    ROOT
    / "state/moon-http/quant-moon-bounded-100-20261023"
    / "v3-real-composite-s7-post-dedup-20261023.json"
)
SIDECAR = (
    ROOT
    / "state/moon-http/quant-v3-parent-sidecar-20261023"
    / "v3-research-parent-candidates.sqlite"
)
COHORT = "v3-3-parent-g452-development-20261023"
BUDGET = ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=15, min_closed_trades=30)


def main() -> None:
    report = json.loads(INPUT.read_text())
    s7 = json.loads(S7_INPUT.read_text())
    expected_head = "e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337"
    assert report["generation_head_hash"] == expected_head
    assert len(report["combinations"]) == 6
    with tempfile.TemporaryDirectory(prefix="quant-v3-sidecar-source-") as tmp:
        state = Path(tmp) / "research"
        path = state / "academic-gpt-checkpoints"
        path.mkdir(parents=True)
        original = SOURCE / "research/academic-gpt-checkpoints"
        for filename in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
            with (
                sqlite3.connect(original / filename) as src,
                sqlite3.connect(path / filename) as dst,
            ):
                src.backup(dst)
        service = AcademicMCPCheckpointService(project_root=ROOT, state_dir=state)
        sid = (SOURCE / "session-id.txt").read_text().strip()
        checkout = checkout_counted_donors(service, sid, (68, 192, 248))
        assert checkout.original_session_head_hash == expected_head
        assert checkout.market.dataset_hash == report["dataset_hash"] == s7["dataset_hash"]
        donors = {x.generation: x for x in checkout.donors}
        measured = {
            i: audit_inherited_decisions(
                checkout.compiled_by_hash[d.strategy_hash], checkout.market
            )
            for i, d in donors.items()
        }
        ledger = ResearchParentSidecar(SIDECAR)
        label = ledger.pin_cohort(
            cohort_id=COHORT,
            source_ledger_head=expected_head,
            dataset_hash=checkout.market.dataset_hash,
            initial_parent_hash=donors[192].strategy_hash,
            source_generations=(68, 192, 248),
        )

        for row in report["combinations"]:
            entry, exit_, risk = (
                donors[row["entry_gen"]],
                donors[row["exit_gen"]],
                donors[row["risk_gen"]],
            )
            composite = compose(entry=entry, exit=exit_, risk=risk)
            base = checkout.compiled_by_hash[entry.strategy_hash]
            child = replace(
                base,
                strategy=composite.strategy,
                strategy_hash=content_hash(
                    composite.strategy.model_dump(
                        mode="json",
                        by_alias=True,
                    )
                ),
            )
            audit = audit_inherited_decisions(child, checkout.market)
            metrics = audit.llm_packet["metrics"]
            risk_review = assess_child_risk(
                parent_equity=measured[entry.generation].evaluation.equity_curve,
                child_equity=audit.evaluation.equity_curve,
                child_closed_trades=len(audit.round_trips),
                budget=BUDGET,
            )
            duplicates = [
                gen
                for gen, parent_audit in measured.items()
                if (
                    audit.evaluation.equity_hash == parent_audit.evaluation.equity_hash
                    and audit.evaluation.trades == parent_audit.evaluation.trades
                )
            ]
            assert row["genome_hash"] == composite.genome_hash
            assert row["strategy_hash"] == child.strategy_hash
            assert row["audit_hash"] == audit.trace_hash
            assert abs(row["return"] - metrics["total_return"]) < 1e-10
            assert abs(row["mdd"] - metrics["max_drawdown"]) < 1e-10
            assert row["closed_trades"] == len(audit.round_trips)
            assert abs(row["cash_costs"] - audit.evaluation.total_paid_costs) < 1e-7
            assert row["risk_eligible"] == risk_review["eligible"]
            assert row["economic_duplicate_of"] == duplicates
            assert row["risk_and_novelty_eligible"] == bool(
                risk_review["eligible"] and not duplicates
            )
            s7_current = (
                s7["genome_hash"] == composite.genome_hash
                and s7["costed_s2_audit_hash"] == audit.trace_hash
            )
            if s7_current:
                assert s7["s7_status"] == "NO_OBSERVED_EFFECT"
                assert s7["source_ledger_head"] == expected_head
            lineage = composite.provenance["lineage"]
            proof = {
                "proposal_id": composite.genome_hash,
                "economic_fingerprint": content_hash(
                    {
                        "equity_hash": audit.evaluation.equity_hash,
                        "fills": [asdict(x) for x in audit.evaluation.trades],
                    }
                ),
                "strategy_hash": child.strategy_hash,
                "audit_hash": audit.trace_hash,
                "dataset_hash": checkout.market.dataset_hash,
                "source_ledger_head": expected_head,
                "donor_generations": [item["source_generation"] for item in lineage],
                "donor_component_hashes": [item["component_hash"] for item in lineage],
                "source_evidence_hashes": [item["source_evidence_hash"] for item in lineage],
                "source_s7_report_hashes": [item["source_report_hash"] for item in lineage],
                "entry_generation": entry.generation,
                "exit_generation": exit_.generation,
                "risk_generation": risk.generation,
                "return": metrics["total_return"],
                "mdd": metrics["max_drawdown"],
                "closed_trades": len(audit.round_trips),
                "risk_eligible": risk_review["eligible"],
                "economic_duplicate_of": duplicates,
                "s7_status": s7["s7_status"] if s7_current else "NOT_RUN",
                "s7_evidence_hash": s7["s7_result_hash"] if s7_current else None,
                "measured_costs": audit.evaluation.total_paid_costs,
                "validation_origin": "COSTED_S2_DEVELOPMENT_REPLAY",
                "model_origin": "SCRIPTED_NOT_GPT",
                "broker_executable": False,
                "oos_approved": False,
            }
            receipt = ledger.record_candidate(label, proof)
            print(
                "SIDECAR_CANDIDATE",
                receipt.sequence,
                f"G{entry.generation}/G{exit_.generation}/G{risk.generation}",
                receipt.decision,
                receipt.event_hash[:14],
                flush=True,
            )
        final = ledger.audit(label)
        assert final["attempt_count"] == 6
        assert final["selected_parent_hash"] == donors[192].strategy_hash
        print(
            "SIDECAR_FINAL",
            json.dumps(
                {
                    "attempt_count": final["attempt_count"],
                    "selected_parent_hash": final["selected_parent_hash"],
                    "last_event_hash": final["last_event_hash"],
                    "counted_gpt_generations": 0,
                    "research_parent_promotions": 0,
                },
                sort_keys=True,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
