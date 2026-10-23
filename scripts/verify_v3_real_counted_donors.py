"""Reproducible V3 read-only academic QQQ 3-parent crossover audit.

Creates temporary clone databases; NEVER extends or writes original checkpoints.
The external model is not called. Scoring is REUSED DEVELOPMENT, not OOS.
"""

from __future__ import annotations

import itertools
import json
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.backtest.p2_policy import ChildRiskBudget, assess_child_risk
from core.integrity.hashes import content_hash
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.llm.composite_crossover_v3 import compose
from research.llm.ledger_donors_v3 import checkout_counted_donors

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "state/moon-http/fresh-20261021"
SOURCE_DB = SOURCE / "research/academic-gpt-checkpoints"
OUTPUT = (
    ROOT
    / "state/moon-http/quant-moon-bounded-100-20261023"
    / "v3-ledger-donor-checkout-dedup-20261023.json"
)
BUDGET = ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=15, min_closed_trades=30)
DONORS = (68, 192, 248)


def _original_checksum() -> tuple[int, str]:
    with sqlite3.connect(
        "file:" + str((SOURCE_DB / "cycles.sqlite").resolve()) + "?mode=ro", uri=True
    ) as db:
        n = db.execute("select count(*) from generations").fetchone()[0]
        head = db.execute(
            "select evidence_hash from generations order by generation desc limit 1"
        ).fetchone()[0]
    return n, head


def main() -> None:
    source_head = _original_checksum()
    assert source_head == (452, "e620bfecb8bd5359731834d87064c13c1a3a32337da1d946a3f132cf9d79b337")
    with tempfile.TemporaryDirectory(prefix="quant-v3-ledger-donor-") as tmpdir:
        state = Path(tmpdir) / "research"
        target = state / "academic-gpt-checkpoints"
        target.mkdir(parents=True)
        for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
            with (
                sqlite3.connect(SOURCE_DB / name) as original,
                sqlite3.connect(target / name) as clone,
            ):
                original.backup(clone)
        svc = AcademicMCPCheckpointService(project_root=ROOT, state_dir=state)
        sid = (SOURCE / "session-id.txt").read_text().strip()
        checked = checkout_counted_donors(svc, sid, DONORS)
        assert checked.original_session_head_hash == source_head[1]
        parents = list(checked.donors)
        originals = {}
        parent_audits = {}
        for parent in parents:
            base = checked.compiled_by_hash[parent.strategy_hash]
            audit = audit_inherited_decisions(base, checked.market)
            parent_audits[parent.generation] = audit
            originals[parent.generation] = {
                "source_evidence_hash": parent.evidence_hash,
                "source_report_hash": parent.report_hash,
                "strategy_hash": parent.strategy_hash,
                "audit_hash": audit.trace_hash,
                "total_return": audit.llm_packet["metrics"]["total_return"],
                "mdd": audit.llm_packet["metrics"]["max_drawdown"],
                "closed_trades": len(audit.round_trips),
            }
        results = []
        for entry, exit_, risk in itertools.permutations(parents, 3):
            candidate = compose(entry=entry, exit=exit_, risk=risk)
            base = checked.compiled_by_hash[entry.strategy_hash]
            compiled = replace(
                base,
                strategy=candidate.strategy,
                strategy_hash=content_hash(
                    candidate.strategy.model_dump(mode="json", by_alias=True)
                ),
            )
            audit = audit_inherited_decisions(compiled, checked.market)
            budget = assess_child_risk(
                parent_equity=parent_audits[entry.generation].evaluation.equity_curve,
                child_equity=audit.evaluation.equity_curve,
                child_closed_trades=len(audit.round_trips),
                budget=BUDGET,
            )
            matched_parent = [
                generation
                for generation, donor_audit in parent_audits.items()
                if audit.evaluation.equity_hash == donor_audit.evaluation.equity_hash
                and audit.evaluation.trades == donor_audit.evaluation.trades
            ]
            row = {
                "entry_gen": entry.generation,
                "exit_gen": exit_.generation,
                "risk_gen": risk.generation,
                "genome_hash": candidate.genome_hash,
                "source_count": len(candidate.strategy.parents),
                "strategy_hash": compiled.strategy_hash,
                "audit_hash": audit.trace_hash,
                "return": audit.llm_packet["metrics"]["total_return"],
                "mdd": audit.llm_packet["metrics"]["max_drawdown"],
                "closed_trades": len(audit.round_trips),
                "cash_costs": audit.evaluation.total_paid_costs,
                "risk_eligible": budget["eligible"],
                "economic_duplicate_of": matched_parent,
                "risk_and_novelty_eligible": bool(budget["eligible"] and not matched_parent),
                "risk_reasons": {k: v for k, v in budget.items() if "pass" in k or "reason" in k},
            }
            results.append(row)
            print("REAL_CROSSOVER", json.dumps(row, ensure_ascii=False), flush=True)
        payload = {
            "schema": "quant-v3-real-counted-donor-multi-parent-audit-dedup-v2",
            "data_zone": "REUSED_DEVELOPMENT_NOT_OOS",
            "dataset_hash": checked.market.dataset_hash,
            "bars": len(checked.market.bars),
            "generation_head_hash": source_head[1],
            "donor_generations": DONORS,
            "donors": originals,
            "risk_budget": BUDGET.model_dump(mode="json"),
            "combinations": results,
            "gpt_per_generation_calls": 0,
            "checkpoint_committed": False,
            "orders_enabled": False,
            "oos_approved": False,
        }
        assert _original_checksum() == source_head
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        if OUTPUT.exists():
            raise RuntimeError("existing research output must not be overwritten")
        OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        print(
            "AUDIT_COMPLETE",
            len(results),
            "PASSED_RISK",
            sum(r["risk_eligible"] for r in results),
            "NOVEL_RISK_PASS",
            sum(r["risk_and_novelty_eligible"] for r in results),
            "OUTPUT",
            OUTPUT,
            flush=True,
        )


if __name__ == "__main__":
    main()
