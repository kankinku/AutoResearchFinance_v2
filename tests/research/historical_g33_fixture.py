"""Frozen G33 test-only archive reconstruction from Phase-1 read-only backup.

Never truncate/rewrite the live state; trim *only* the temporary SQLite clones.
Original 33 evidence hashes are retained without rewriting any evidence row.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.integrity.hashes import content_hash
from evaluation.academic_campaign_audit import _validate_snapshot
from tests.research.test_lineage_p0_3 import ROOT, SID

SNAPSHOT = ROOT / "state/moon-http/research/audits/phase1-20261017-1950"
FROZEN_G33_EVIDENCE = "940efd8e38416502a06c003aa672ac148861e244fa138b9525d7028aac65b27b"
FROZEN_G29_EVIDENCE = "167e8c2095e13819f38e9c62637e1c8426e1bf8d89c69d03cf0e860a7da9b3b2"


def _backup(src: Path, dst: Path) -> None:
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as original:
        with sqlite3.connect(dst) as clone:
            original.backup(clone)


def copy_historical_g33_checkpoint(path: Path) -> Path:
    """Create new isolated G33 with pinned evidence G29/G33 and staged G34.

    G34 parent selection already existed at the boundary and must be preserved,
    while all future selectors/reports/receipts must be removed from the copy.
    """
    _validate_snapshot(SNAPSHOT)
    dst = path / "academic-gpt-checkpoints"
    dst.mkdir(exist_ok=False)
    for filename in ("cycles.sqlite", "gateway.sqlite"):
        _backup(SNAPSHOT / filename, dst / filename)
    # The catalog was independently copied and verified during Phase1 replay.
    _backup(SNAPSHOT / "catalog-for-risk-replay.sqlite", dst / "catalog-s6-v2.sqlite")
    with sqlite3.connect(dst / "cycles.sqlite") as db:
        pins = dict(
            db.execute(
                "SELECT generation,evidence_hash FROM generations "
                "WHERE session_id=? AND generation IN (29,33)",
                (SID,),
            ).fetchall()
        )
        if pins != {29: FROZEN_G29_EVIDENCE, 33: FROZEN_G33_EVIDENCE}:
            raise ValueError("immutable historical checkpoint fingerprint mismatch")
        with db:
            db.execute("DELETE FROM generations WHERE session_id=? AND generation>33", (SID,))
            db.execute(
                "UPDATE sessions SET completed=33,status='AWAITING_PROVIDER',"
                "running_token=NULL,error_type=NULL WHERE id=?",
                (SID,),
            )
        verified = db.execute(
            "SELECT COUNT(*) FROM generations WHERE session_id=?", (SID,)
        ).fetchone()[0]
        if verified != 33:
            raise ValueError("incomplete archived history for G33")
    with sqlite3.connect(dst / "gateway.sqlite") as db:
        with db:
            for table in ("experiment_reports", "generation_timings"):
                db.execute(f"DELETE FROM {table} WHERE session_id=? AND generation>33", (SID,))
            db.execute(
                "DELETE FROM successor_lineages WHERE session_id=? AND origin_generation>33",
                (SID,),
            )
            db.execute(
                "DELETE FROM parent_selections WHERE session_id=? AND next_generation>34",
                (SID,),
            )
            for table in ("submission_receipts", "recovery_receipts"):
                db.execute(f"DELETE FROM {table} WHERE session_id=?", (SID,))
            db.execute(
                "UPDATE stages SET phase='AWAITING_PLAN',token=?,plan_json=NULL,"
                "plan_digest=NULL,context_digest=NULL WHERE session_id=?",
                ("5" * 32, SID),
            )
        evidence = db.execute(
            "SELECT selection_json,selection_hash FROM parent_selections "
            "WHERE session_id=? AND next_generation=34",
            (SID,),
        ).fetchone()
        if evidence is None:
            raise ValueError("missing frozen historical G34 selected parent")
        import json

        selection = json.loads(evidence[0])
        if (
            selection["source_generation"] != 29
            or content_hash({k: v for k, v in selection.items() if k != "selection_hash"})
            != evidence[1]
        ):
            raise ValueError("tampered historical G34 pinned selection")
    return dst
