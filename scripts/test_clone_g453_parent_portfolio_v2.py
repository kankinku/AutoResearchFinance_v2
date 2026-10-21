"""Real G453/G454 checkpoint cycles with an opt-in P1 parent in an isolated clone.

Proves: audited parent -> ResearchIntent mutation -> S2 diagnosis -> S7 report
-> immutable G453 evidence. The production G452 session is never extended.
This reuses the deterministic historical controller, NOT a per-generation GPT.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.integrity.hashes import content_hash
from scripts import fresh_development_cohort_controller_20261021 as controller

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state/moon-http/fresh-20261021"
ORIGINAL = STATE / "research/academic-gpt-checkpoints"
SID = (STATE / "session-id.txt").read_text().strip()


def head_digest() -> tuple[int, str]:
    with sqlite3.connect(ORIGINAL / "cycles.sqlite") as db:
        rows = db.execute(
            "SELECT generation,evidence_hash FROM generations ORDER BY generation"
        ).fetchall()
    return len(rows), content_hash(rows)


def main() -> None:
    original = head_digest()
    assert original[0] == 452, original
    with tempfile.TemporaryDirectory(prefix="quant-p1-g453-g454-real-cycle-") as temp:
        base = Path(temp)
        copied = base / "academic-gpt-checkpoints"
        copied.mkdir()
        checksums = {}
        for filename in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
            with sqlite3.connect(ORIGINAL / filename) as src:
                with sqlite3.connect(copied / filename) as dst:
                    src.backup(dst)
            with sqlite3.connect(copied / filename) as db:
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            checksums[filename] = hashlib.sha256((copied / filename).read_bytes()).hexdigest()
        service = AcademicMCPCheckpointService(
            project_root=ROOT, state_dir=base, parent_portfolio_v2=True
        )
        initial = service.get({"session_id": SID})
        assert initial["status"] == "COMPLETED" and initial["completed_generations"] == 452
        expanded = service.extend_completed_session(SID, additional_generations=2)
        assert expanded["completed_generations"] == 452
        assert expanded["requested_generations"] == 454
        assert expanded["checkpoint_phase"] == "AWAITING_PLAN"
        pinned = expanded["model_context"]["selected_development_parent"]
        assert pinned is not None and pinned["source_kind"] == "COUNTED_GENERATION"
        print(
            "AUDITED_PARENT",
            pinned["source_generation"],
            pinned["successor_strategy_hash"],
            flush=True,
        )
        # Controller global replacements are strictly process-scoped; the
        # gateway only sees the cloned DB, and log writes only in temp.
        with (
            patch.object(controller, "AcademicMCPCheckpointService", return_value=service),
            patch.object(controller, "PROGRESS", base / "clone-progress.jsonl"),
            patch.object(controller, "SESSION", SID),
        ):
            controller.main(2)
        final = service.get({"session_id": SID})
        assert final["completed_generations"] == final["requested_generations"] == 454
        assert final["status"] == final["checkpoint_phase"] == "COMPLETED"
        assert final["final_report"]["all_proposed_hypotheses_measured"] is True
        history = final["history"]
        assert len(history) == 454
        first_child, second_child = history[-2:]
        assert first_child["generation"] == 453
        assert second_child["generation"] == 454
        assert first_child["previous_evidence_hash"] == history[-3]["evidence_hash"]
        assert second_child["previous_evidence_hash"] == first_child["evidence_hash"]
        assert first_child["inherited_parent"]["source_generation"] == pinned["source_generation"]
        assert (
            first_child["inherited_parent"]["parent_strategy_hash"]
            == pinned["successor_strategy_hash"]
        )
        assert first_child["inherited_parent"]["parent_selection_hash"] == pinned["selection_hash"]
        assert (
            second_child["inherited_parent"]["source_generation"]
            != first_child["inherited_parent"]["source_generation"]
        )
        for current in (first_child, second_child):
            assert current["inherited_strategy_ir"] is not None
        assert final["orders_enabled"] is False
        assert final["independent_oos_approved"] is False
        with service._connect() as db:
            count = db.execute(
                "SELECT count(*) FROM experiment_reports WHERE session_id=?", (SID,)
            ).fetchone()[0]
            reports = [service._stored_experiment(db, SID, gen) for gen in (453, 454)]
        assert count == 454, count
        for child, report in zip((first_child, second_child), reports, strict=True):
            assert report is not None
            assert report["original_generation_evidence_hash"] == child["evidence_hash"]
        assert head_digest() == original, "PRODUCTION_EVIDENCE_WAS_CHANGED"
        result = {
            "mode": "ISOLATED_CLONE_REAL_G453_G454_DETERMINISTIC_CONTROLLER",
            "original_generations": original[0],
            "original_head_digest": original[1],
            "original_unchanged": True,
            "snapshot_sha256": checksums,
            "cloned_completed": final["completed_generations"],
            "cloned_requested": final["requested_generations"],
            "selected_parent_source": pinned["source_generation"],
            "parent_lane_origins": pinned["candidate_review"]["lane_source_generations"],
            "parent_selection_hash": pinned["selection_hash"],
            "new_generations": [
                {
                    "generation": child["generation"],
                    "parent_generation": child["inherited_parent"]["source_generation"],
                    "child_strategy_hash": child["strategy_hash"],
                    "child_evidence_hash": child["evidence_hash"],
                    "parent_prior_evidence_hash": child["previous_evidence_hash"],
                    "metrics": child["metrics"],
                    "experiment_report_hash": report["record_hash"],
                }
                for child, report in zip((first_child, second_child), reports, strict=True)
            ],
            "s7_count": count,
            "live_orders": False,
            "independent_oos": False,
            "independently_gpt_authored": False,
        }
        output = STATE / "p1-g453-g454-clone-e2e-result.json"
        if output.exists():
            raise RuntimeError("DO_NOT_OVERWRITE_PREVIOUS_E2E_RESULT")
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print("PASS_REAL_CLONE_G453_G454", json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
