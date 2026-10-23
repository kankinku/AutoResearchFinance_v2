"""Read-only operator P2 portfolio evidence audit against a chosen GPT MCP session.

Creates two short-lived SQLite copies. One confirms an already pinned next
parent survives opt-in; the other clears ONLY the clone's next pin to compare
unmodified legacy vs reviewed V2 candidate inclusion and selection.

No OAuth calls or changes, orders, OOS, live writes, or paid model calls.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from application.academic_checkpoint_service import AcademicMCPCheckpointService


def _copy_store(source: Path, target: Path) -> None:
    target.mkdir()
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        original = source / name
        if not original.is_file():
            raise RuntimeError("Quant parent audit source is incomplete")
        with sqlite3.connect(original.resolve().as_uri() + "?mode=ro", uri=True) as read:
            if read.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Quant parent audit source integrity failed")
            with sqlite3.connect(target / name) as write:
                read.backup(write)


def audit(*, project_root: Path, state_dir: Path, session_id: str) -> dict[str, object]:
    if re.fullmatch(r"[a-f0-9]{32}", session_id) is None:
        raise ValueError("invalid P2 audited session ID")
    project_root = project_root.resolve()
    state_dir = state_dir.resolve()
    source = state_dir / "academic-gpt-checkpoints"
    with TemporaryDirectory(prefix="quant-p2-shadow-") as first:
        dir1 = Path(first)
        _copy_store(source, dir1 / "academic-gpt-checkpoints")
        service1 = AcademicMCPCheckpointService(
            project_root=project_root, state_dir=dir1, parent_portfolio_v2=True
        )
        pinned = service1.get({"session_id": session_id})
        if pinned["checkpoint_phase"] not in ("AWAITING_PLAN", "COMPLETED"):
            raise RuntimeError("P2 shadow requires a safe planning checkpoint")
        next_generation = pinned["completed_generations"] + 1
        current = pinned["model_context"]["selected_development_parent"]
        with TemporaryDirectory(prefix="quant-p2-comparison-") as second:
            dir2 = Path(second)
            _copy_store(source, dir2 / "academic-gpt-checkpoints")
            with sqlite3.connect(dir2 / "academic-gpt-checkpoints/gateway.sqlite") as db:
                db.execute(
                    "DELETE FROM parent_selections WHERE session_id=? AND next_generation=?",
                    (session_id, next_generation),
                )
            comparison = AcademicMCPCheckpointService(
                project_root=project_root,
                state_dir=dir2,
                parent_portfolio_v2=True,
            ).get({"session_id": session_id})
            selected = comparison["model_context"]["selected_development_parent"]
            evidence = pinned["history"][-1]["evidence_hash"]
            # Re-read both originals after shadow work to guarantee no writing.
            current_live = AcademicMCPCheckpointService(
                project_root=project_root,
                state_dir=state_dir,
            ).get({"session_id": session_id})
            if (
                current_live["completed_generations"] != pinned["completed_generations"]
                or current_live["history"][-1]["evidence_hash"] != evidence
                or current_live["checkpoint_phase"] != pinned["checkpoint_phase"]
            ):
                raise RuntimeError("live ledger changed during P2 shadow comparison")
            return {
                "schema": "quant-p2-scoped-shadow-v1",
                "status": "SHADOW_ONLY_NOT_ACTIVATION",
                "session_id": session_id,
                "completed_generations": pinned["completed_generations"],
                "requested_generations": pinned["requested_generations"],
                "next_generation": next_generation,
                "pinned_parent_unchanged": {
                    "source_kind": current["source_kind"],
                    "source_generation": current["source_generation"],
                    "source_evidence_hash": current["source_evidence_hash"],
                    "selection_hash": current["selection_hash"],
                },
                "v2_if_unpinned": {
                    "source_kind": selected["source_kind"],
                    "source_generation": selected["source_generation"],
                    "return": selected["parent_quality"]["total_return"],
                    "max_drawdown": selected["parent_quality"]["max_drawdown"],
                    "candidate_review": selected.get("candidate_review"),
                },
                "current_evidence_hash_unchanged": evidence,
                "no_orders": True,
                "oos_approved": False,
            }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            audit(
                project_root=args.project_root,
                state_dir=args.state_dir,
                session_id=args.session_id,
            ),
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
