"""T4 frozen historical-G33 checkpoint must not depend on current live count."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tests.research.historical_g33_fixture import copy_historical_g33_checkpoint
from tests.research.test_lineage_p0_3 import ROOT, SID

SNAP = ROOT / "state/moon-http/research/audits/phase1-20261017-1950"


def test_fixed_g33_snapshot_preserves_source_and_exact_historical_hash(tmp_path: Path) -> None:
    with sqlite3.connect(f"file:{SNAP / 'cycles.sqlite'}?mode=ro", uri=True) as origin:
        original = origin.execute(
            "SELECT evidence_hash FROM generations WHERE session_id=? AND generation=33",
            (SID,),
        ).fetchone()[0]
        original_size = origin.execute(
            "SELECT COUNT(*) FROM generations WHERE session_id=?", (SID,)
        ).fetchone()[0]
    destination = copy_historical_g33_checkpoint(tmp_path)
    with sqlite3.connect(destination / "cycles.sqlite") as clone:
        assert (
            clone.execute("SELECT completed FROM sessions WHERE id=?", (SID,)).fetchone()[0] == 33
        )
        assert (
            clone.execute("SELECT COUNT(*) FROM generations WHERE session_id=?", (SID,)).fetchone()[
                0
            ]
            == 33
        )
        assert (
            clone.execute(
                "SELECT evidence_hash FROM generations WHERE session_id=? AND generation=33",
                (SID,),
            ).fetchone()[0]
            == original
        )
    with sqlite3.connect(destination / "gateway.sqlite") as clone:
        assert (
            clone.execute("SELECT phase FROM stages WHERE session_id=?", (SID,)).fetchone()[0]
            == "AWAITING_PLAN"
        )
        assert (
            clone.execute(
                "SELECT COUNT(*) FROM experiment_reports WHERE session_id=?", (SID,)
            ).fetchone()[0]
            == 33
        )
        assert (
            clone.execute(
                "SELECT COUNT(*) FROM parent_selections WHERE session_id=?", (SID,)
            ).fetchone()[0]
            == 1
        )
        assert (
            clone.execute(
                "SELECT COUNT(*) FROM submission_receipts WHERE session_id=?", (SID,)
            ).fetchone()[0]
            == 0
        )
    with sqlite3.connect(f"file:{SNAP / 'cycles.sqlite'}?mode=ro", uri=True) as origin:
        assert (
            origin.execute(
                "SELECT COUNT(*) FROM generations WHERE session_id=?", (SID,)
            ).fetchone()[0]
            == original_size
        )
