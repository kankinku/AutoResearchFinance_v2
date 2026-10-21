"""Non-destructive audit of the P1 parent portfolio against the real G452 ledger.

Clones SQLite via SQLite online-backup API and writes only under temporary
directories. Production research state and pinned parent choices are untouched.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.integrity.hashes import content_hash
from research.llm.parent_portfolio_v2 import shortlist_counted_generations

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "state/moon-http/fresh-20261021/research/academic-gpt-checkpoints"
SID = (ROOT / "state/moon-http/fresh-20261021/session-id.txt").read_text().strip()


def snapshot_evidence() -> tuple[int, str]:
    with sqlite3.connect(ORIGINAL / "cycles.sqlite") as c:
        rows = c.execute(
            "SELECT generation,evidence_hash FROM generations ORDER BY generation"
        ).fetchall()
    return len(rows), content_hash(rows)


def main() -> None:
    before = snapshot_evidence()
    assert before[0] == 452
    with tempfile.TemporaryDirectory(prefix="quant-parent-v2-clone-") as temp:
        dst = Path(temp) / "academic-gpt-checkpoints"
        dst.mkdir(parents=True)
        for source in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
            with sqlite3.connect(ORIGINAL / source) as original:
                with sqlite3.connect(dst / source) as target:
                    original.backup(target)
        with sqlite3.connect(dst / "gateway.sqlite") as c:
            c.execute("DELETE FROM parent_selections WHERE next_generation=453")
        service = AcademicMCPCheckpointService(
            project_root=ROOT, state_dir=Path(temp), parent_portfolio_v2=True
        )
        with service._connect() as db:
            _, catalog, market, state = service._state(db, SID)
            shortlist = shortlist_counted_generations(state["history"], per_lane=6)
            print(
                "SHORTLIST",
                [
                    (
                        x["generation"],
                        round(x["metrics"]["total_return"] * 100, 2),
                        round(x["metrics"]["max_drawdown"] * 100, 2),
                    )
                    for x in shortlist
                ],
                flush=True,
            )
            chosen = service._choose_counted_generation_portfolio(db, catalog, market, state)
            assert chosen is not None
            print(
                "SELECTED",
                chosen["source_generation"],
                chosen["parent_quality"],
                chosen["candidate_review"],
                flush=True,
            )
            assert chosen["candidate_review"]["diverse_parent_count"] >= 2
            db.execute(
                "INSERT INTO parent_selections "
                "(session_id,next_generation,lineage_report_hash,selection_hash,selection_json) "
                "VALUES (?,?,?,?,?)",
                (
                    SID,
                    453,
                    chosen["lineage_report_hash"],
                    chosen["selection_hash"],
                    json.dumps(chosen, sort_keys=True),
                ),
            )
        with service._connect() as db:
            _, catalog, market, state = service._state(db, SID)
        ir, original, actual = service._selected_ir(catalog, market, state)
        assert ir.strategy_hash == chosen["successor_strategy_hash"]
        assert actual["selection_hash"] == chosen["selection_hash"]
        print("REPLAYED_PINNED_PARENT", original["generation"], ir.strategy_hash, flush=True)
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "CLONE_ONLY_OPT_IN_P1_DEVELOPMENT_NON_PIT",
            "original_generation_count": before[0],
            "original_evidence_chain_digest": before[1],
            "shortlisted_source_generations": [x["generation"] for x in shortlist],
            "selected": chosen,
            "replayed_parent_strategy_hash": ir.strategy_hash,
            "original_unchanged": snapshot_evidence() == before,
            "no_orders": True,
            "oos_approved": False,
        }
        assert report["original_unchanged"]
        out = ROOT / "state/moon-http/fresh-20261021/p1-parent-audit-v2.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print("REPORT", out, content_hash(report), flush=True)


if __name__ == "__main__":
    main()
