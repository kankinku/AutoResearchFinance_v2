"""Read-only G452-counted donor to V3 S2/P2/S7 integration experiment.

Creates ephemeral SQLite backup copies only. S7 hypothesis is explicitly
SCRIPTED from the costed child audit, not from an authenticated GPT provider.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget, assess_child_risk
from core.integrity.hashes import content_hash
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.inherited_experiments import compare_inherited_experiments
from research.llm.composite_crossover_v3 import compose
from research.llm.composite_validation_v3 import CompositeValidationError, validate_composite
from research.llm.diagnostic_research import build_diagnostic_context
from research.llm.ledger_donors_v3 import checkout_counted_donors

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "state/moon-http/fresh-20261021"
DB = SOURCE / "research/academic-gpt-checkpoints"
OUTPUT = (
    ROOT
    / "state/moon-http/quant-moon-bounded-100-20261023"
    / "v3-real-composite-s7-post-dedup-20261023.json"
)


def _snapshot(target: Path) -> None:
    target.mkdir(parents=True)
    for f in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        with sqlite3.connect(DB / f) as src, sqlite3.connect(target / f) as dest:
            src.backup(dest)


def main() -> None:
    sid = (SOURCE / "session-id.txt").read_text().strip()
    with tempfile.TemporaryDirectory(prefix="quant-v3-s7-") as tmp:
        state = Path(tmp) / "research"
        _snapshot(state / "academic-gpt-checkpoints")
        svc = AcademicMCPCheckpointService(project_root=ROOT, state_dir=state)
        sources = checkout_counted_donors(svc, sid, (192, 248, 68))
        entry, exit_, risk = sources.donors
        child = compose(entry=entry, exit=exit_, risk=risk)
        compiled_parent = sources.compiled_by_hash[entry.strategy_hash]
        compiled_child = replace(
            compiled_parent,
            strategy=child.strategy,
            strategy_hash=content_hash(child.strategy.model_dump(mode="json", by_alias=True)),
        )
        audit = audit_inherited_decisions(compiled_child, sources.market)
        ctx = build_diagnostic_context(audit, compiled_child.strategy)
        obs = ctx["observations"]["execution_samples"][0]
        exit_condition = child.strategy.exit.conditions[0]
        # Advance/defer one scalar cut-off, nothing else; proof binds exact
        # previous strategy/market and remains classified SCRIPTED_CONTROL.
        new_cut = 0.25 if exit_condition.value == 0.5 else 0.5
        condition = exit_condition.model_dump(mode="json")
        condition["value"] = new_cut
        script_hypothesis = {
            "context_hash": ctx["context_hash"],
            "audit_hash": audit.trace_hash,
            "strategy_hash": audit.evaluation.strategy_hash,
            "dataset_hash": audit.evaluation.dataset_hash,
            "summary": "Scripted single exit threshold ablation on unchanged QQQ development data.",
            "hypotheses": [
                {
                    "hypothesis_id": "v3_real_scripted_exit_ablation_01",
                    "observed_ids": [obs["trade_id"], obs["decision_id"]],
                    "mechanism": "Changing the close-exit threshold may alter a verified fill.",
                    "alternative": "The exit change may hurt returns and raise drawdown.",
                    "expected_metric": "max_drawdown",
                    "predicted_direction": "DECREASE",
                    "test_design": "RULE_STRUCTURE",
                    "control": "PARENT_UNCHANGED",
                    "next_intent": {
                        "mode": "structure",
                        "parent_ids": [child.strategy.strategy_id],
                        "operations": [
                            {
                                "op": "REPLACE_RULE",
                                "path": "exit.conditions.0",
                                "condition": condition,
                            }
                        ],
                        "rationale": (
                            "Controlled one-threshold experiment; no model-generated proposal."
                        ),
                    },
                }
            ],
        }
        budget = ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=15, min_closed_trades=30)
        parent_audit = audit_inherited_decisions(compiled_parent, sources.market)
        risk_review = assess_child_risk(
            parent_equity=parent_audit.evaluation.equity_curve,
            child_equity=audit.evaluation.equity_curve,
            child_closed_trades=len(audit.round_trips),
            budget=budget,
        )
        assert risk_review["eligible"], risk_review
        try:
            validate_composite(
                child,
                sources.compiled_by_hash,
                sources.market,
                budget=budget,
                diagnosis=script_hypothesis,
            )
        except CompositeValidationError as exc:
            assert "economic duplicate" in str(exc), str(exc)
            rejection = str(exc)
        else:
            raise RuntimeError("economically identical child was improperly promoted")
        # Inspect the control, but deliberately DO NOT promote a clone of G192.
        s7 = compare_inherited_experiments(
            compiled_child,
            sources.market,
            script_hypothesis,
            parent_proof_hash=child.genome_hash,
        )
        trial = s7.experiments[0]
        output = {
            "schema": "v3-real-counted-multiparent-s7-post-dedup-v1",
            "promotion_eligible": False,
            "rejection_reason": rejection,
            "source": "ISOLATED_G452_DEV",
            "donor_gens": [d.generation for d in sources.donors],
            "donor_strategy_hashes": [d.strategy_hash for d in sources.donors],
            "donor_evidence_hashes": [d.evidence_hash for d in sources.donors],
            "donor_s7_report_hashes": [d.report_hash for d in sources.donors],
            "genome_hash": child.genome_hash,
            "source_ledger_head": sources.original_session_head_hash,
            "dataset_hash": sources.market.dataset_hash,
            "bars": len(sources.market.bars),
            "costed_s2_audit_hash": audit.trace_hash,
            "child_total_return": audit.llm_packet["metrics"]["total_return"],
            "child_mdd": audit.llm_packet["metrics"]["max_drawdown"],
            "child_closed_trades": len(audit.round_trips),
            "p2_review": risk_review,
            "s7_audit_hash": s7.audit_hash,
            "s7_status": trial.status,
            "s7_predicted_direction": script_hypothesis["hypotheses"][0]["predicted_direction"],
            "s7_result_direction": trial.status,
            "s7_parent_equity": trial.parent_final_equity,
            "s7_child_equity": trial.child_final_equity,
            "s7_parent_mdd": trial.parent_metric,
            "s7_child_mdd": trial.child_metric,
            "s7_result_hash": s7.evidence_hash,
            "model_origin": "SCRIPTED_CONTROL_NOT_GPT",
            "counted_generation_committed": False,
            "orders_enabled": False,
            "independent_oos_approved": False,
        }
        if OUTPUT.exists():
            raise RuntimeError("existing S7 result protected from overwrite")
        OUTPUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(
            "REAL_S2_P2_S7_DUPLICATE_REJECTED", json.dumps(output, ensure_ascii=False), flush=True
        )


if __name__ == "__main__":
    main()
