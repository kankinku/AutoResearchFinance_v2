"""Read canonical Quant gateway S7 receipts with *strictly* read-only SQLite.

Unlike evaluate_algorithm_experiments, this module never computes or persists
missing S7 evidence. It is a private preflight, not an MCP/public host action.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from application.research_handoff_builder import (
    ResearchHandoffError,
    _check_receipts,
    _check_snapshot,
)
from core.integrity.hashes import content_hash
from research.llm.autonomous_cycle import AcademicCycleService


class EvidenceReadError(ResearchHandoffError):
    """Canonical SQLite cannot establish complete S7 evidence without writes."""


def _open_existing_readonly(stack: ExitStack, path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise EvidenceReadError("missing or symlinked evidence SQLite database")
    # URI is constructed from the literal filesystem path and never contains
    # query arguments from callers. No connect-to-create, migrations, WAL pragma.
    db = stack.enter_context(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def read_committed_s7(
    academic_checkpoint_dir: Path,
    snapshot: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """Load already-stored S7, bound to the exact canonical generation snapshot.

    A complete caller snapshot must be obtained from Quant itself, not a local
    summary or editable handoff. Two read transactions are verified against it;
    the next consumer must still re-check freshness before any submission.
    """
    try:
        sid, history = _check_snapshot(snapshot)
        if academic_checkpoint_dir.is_symlink() or not academic_checkpoint_dir.is_dir():
            raise EvidenceReadError("missing or symlinked academic checkpoint directory")
        with ExitStack() as stack:
            cycle = _open_existing_readonly(stack, academic_checkpoint_dir / "cycles.sqlite")
            gateway = _open_existing_readonly(stack, academic_checkpoint_dir / "gateway.sqlite")
            current = cycle.execute(
                "SELECT requested,completed,status,dataset_hash FROM sessions WHERE id=?", (sid,)
            ).fetchone()
            if (
                current is None
                or current["requested"] != snapshot["requested_generations"]
                or current["completed"] != snapshot["completed_generations"]
                or current["status"] != snapshot["status"]
                or current["dataset_hash"] != snapshot["dataset_hash"]
            ):
                raise EvidenceReadError("stale canonical research snapshot or session mismatch")
            phase = gateway.execute(
                "SELECT phase,catalog_version FROM stages WHERE session_id=?", (sid,)
            ).fetchone()
            if (
                phase is None
                or phase["phase"] != snapshot["checkpoint_phase"]
                or phase["catalog_version"] != snapshot["catalog_version"]
            ):
                raise EvidenceReadError("stale canonical gateway phase or catalog")
            saved = cycle.execute(
                "SELECT generation,evidence_json,evidence_hash FROM generations "
                "WHERE session_id=? ORDER BY generation",
                (sid,),
            ).fetchall()
            if len(saved) != len(history):
                raise EvidenceReadError("canonical generation snapshot length changed")
            prior = None
            for generation, (stored, source) in enumerate(zip(saved, history, strict=True), 1):
                try:
                    raw = json.loads(stored["evidence_json"])
                except (TypeError, ValueError) as exc:
                    raise EvidenceReadError("canonical generation JSON corrupt") from exc
                expected = AcademicCycleService._row_evidence_hash(sid, generation, prior, raw)
                if (
                    stored["generation"] != generation
                    or stored["evidence_hash"] != expected
                    or source != {**raw, "evidence_hash": expected}
                ):
                    raise EvidenceReadError("canonical snapshot evidence differs from disk")
                prior = expected
            rows = gateway.execute(
                "SELECT generation,report_json,report_hash FROM experiment_reports "
                "WHERE session_id=? ORDER BY generation",
                (sid,),
            ).fetchall()
            if len(rows) != len(history):
                raise EvidenceReadError("missing committed S7 receipts; no recomputation")
            receipts: dict[int, dict[str, Any]] = {}
            for row in rows:
                try:
                    body = json.loads(row["report_json"])
                except (TypeError, ValueError) as exc:
                    raise EvidenceReadError("S7 malformed JSON") from exc
                if (
                    not isinstance(body, dict)
                    or content_hash(body) != row["report_hash"]
                    or type(row["generation"]) is not int
                    or row["generation"] in receipts
                ):
                    raise EvidenceReadError("S7 persisted digest or generation invalid")
                receipts[row["generation"]] = {**body, "record_hash": row["report_hash"]}
            _check_receipts(sid, history, receipts)
            return receipts
    except EvidenceReadError:
        raise
    except (ResearchHandoffError, sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
        raise EvidenceReadError(f"canonical snapshot/S7 evidence invalid: {exc}") from exc


def read_research_bundle_readonly(
    academic_checkpoint_dir: Path,
    session_id: str,
) -> dict[str, Any]:
    """Create a token-free snapshot from read-only cycle+gateway SQL evidence.

    Both databases are read as independent committed snapshots. The subsequent
    read_committed_s7 check detects changes between those reads by comparing
    the EXACT validated full history, session and gateway phase. No OAuth,
    stage token, market data, or extra experiment is loaded.
    """
    import re

    if not isinstance(session_id, str) or re.fullmatch(r"[0-9a-f]{32}", session_id) is None:
        raise EvidenceReadError("invalid research session identifier")
    if academic_checkpoint_dir.is_symlink() or not academic_checkpoint_dir.is_dir():
        raise EvidenceReadError("missing or symlinked academic checkpoint directory")
    try:
        with ExitStack() as stack:
            cycle = _open_existing_readonly(stack, academic_checkpoint_dir / "cycles.sqlite")
            gateway = _open_existing_readonly(stack, academic_checkpoint_dir / "gateway.sqlite")
            session = cycle.execute(
                "SELECT requested,completed,status,dataset_hash FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise EvidenceReadError("session not present in canonical cycle")
            phase = gateway.execute(
                "SELECT phase,catalog_version FROM stages WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if phase is None:
                raise EvidenceReadError("session not present in canonical gateway")
            rows = cycle.execute(
                "SELECT generation,evidence_json,evidence_hash FROM generations "
                "WHERE session_id=? ORDER BY generation",
                (session_id,),
            ).fetchall()
            history: list[dict[str, Any]] = []
            prev: str | None = None
            for n, stored in enumerate(rows, 1):
                original = json.loads(stored["evidence_json"])
                digest = AcademicCycleService._row_evidence_hash(
                    session_id,
                    n,
                    prev,
                    original,
                )
                if (
                    stored["generation"] != n
                    or digest != stored["evidence_hash"]
                    or original.get("previous_evidence_hash") != prev
                ):
                    raise EvidenceReadError("canonical generation hash chain invalid")
                history.append({**original, "evidence_hash": digest})
                prev = digest
            snapshot = {
                "session_id": session_id,
                "requested_generations": session["requested"],
                "completed_generations": session["completed"],
                "status": session["status"],
                "dataset_hash": session["dataset_hash"],
                "catalog_version": phase["catalog_version"],
                "checkpoint_phase": phase["phase"],
                "history": history,
                "orders_enabled": False,
                "independent_oos_approved": False,
            }
        # This is an intentionally *second* independent read for concurrent
        # head/phase changes; no generated state is silently accepted.
        receipts = read_committed_s7(academic_checkpoint_dir, snapshot)
        return {"snapshot": snapshot, "receipts": receipts}
    except EvidenceReadError:
        raise
    except (sqlite3.DatabaseError, ResearchHandoffError, ValueError, TypeError, KeyError) as exc:
        raise EvidenceReadError(f"canonical session read failed: {exc}") from exc
