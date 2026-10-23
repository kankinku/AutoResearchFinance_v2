"""Prove counted V3 parent checkout fails closed on tampered clone history/S7."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from research.llm.ledger_donors_v3 import checkout_counted_donors

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "state/moon-http/fresh-20261021"
SRC_DB = SOURCE / "research/academic-gpt-checkpoints"
SID = (SOURCE / "session-id.txt").read_text().strip()


def _copy(tgt: Path) -> None:
    tgt.mkdir(parents=True)
    for name in ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite"):
        with sqlite3.connect(SRC_DB / name) as source, sqlite3.connect(tgt / name) as dest:
            source.backup(dest)


def _try_tampered(kind: str) -> None:
    with tempfile.TemporaryDirectory(prefix="quant-v3-tamper-") as directory:
        state = Path(directory) / "research"
        target = state / "academic-gpt-checkpoints"
        _copy(target)
        if kind == "evidence":
            with sqlite3.connect(target / "cycles.sqlite") as db:
                db.execute(
                    "UPDATE generations SET evidence_json='{}' WHERE generation=68",
                )
        elif kind == "s7":
            with sqlite3.connect(target / "gateway.sqlite") as db:
                db.execute(
                    "UPDATE experiment_reports SET report_json='{}' WHERE generation=192",
                )
        else:
            raise ValueError("bad tamper trial")
        svc = AcademicMCPCheckpointService(project_root=ROOT, state_dir=state)
        try:
            checkout_counted_donors(svc, SID, (68, 192, 248))
        except ValueError as exc:
            print("FAIL_CLOSED_PASS", kind, type(exc).__name__, str(exc)[:110], flush=True)
        else:
            raise AssertionError(f"corrupt {kind} record accepted")


if __name__ == "__main__":
    _try_tampered("evidence")
    _try_tampered("s7")
