"""Read-only cross-store reconciliation and fail-closed resume preflight.

Canonical SQLite entries corroborate an absent auxiliary JSONL *observation*.
They cannot retroactively create its original event, attest a model provider,
or authorize a new generation. No database writes or model calls occur here.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from application.python_mcp_research_audit import audit_python_mcp_cohort
from core.integrity.hashes import content_hash


def _readonly_db(path: Path, allowed_root: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise ValueError("required canonical checkpoint database missing or symlinked")
    if not path.resolve().is_relative_to(allowed_root):
        raise ValueError("checkpoint database escapes isolated study directory")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def _verified_sqlite_diagnosis(
    cycles: sqlite3.Connection,
    gateway: sqlite3.Connection,
    session_id: str,
    generation: int,
) -> bool:
    """Corroborate a commit against both S7 and timing evidence in gateway."""
    try:
        row = cycles.execute(
            "SELECT evidence_hash FROM generations WHERE session_id=? AND generation=?",
            (session_id, generation),
        ).fetchone()
        if row is None:
            return False
        evidence_hash = row[0]
        timings = gateway.execute(
            "SELECT evidence_hash,end_utc FROM generation_timings "
            "WHERE session_id=? AND generation=?",
            (session_id, generation),
        ).fetchall()
        reviews = gateway.execute(
            "SELECT review_json,review_hash FROM p4_s7_approvals "
            "WHERE session_id=? AND generation=?",
            (session_id, generation),
        ).fetchall()
        if (
            len(timings) != 1
            or len(reviews) != 1
            or timings[0][0] != evidence_hash
            or not timings[0][1]
        ):
            return False
        review = json.loads(reviews[0][0])
        return (
            isinstance(review, dict)
            and review.get("generation") == generation
            and review.get("counted_evidence_hash") == evidence_hash
            and content_hash(review) == reviews[0][1]
        )
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        return False


def reconcile_python_mcp_cohort(root: Path, work_dir: Path) -> dict[str, Any]:
    """Inspect existing study; return safe resume gate without taking any action."""
    base = audit_python_mcp_cohort(root, work_dir)
    work = work_dir.resolve(strict=True)
    session_id = json.loads((work / "session.json").read_text(encoding="utf-8"))["session_id"]
    db_root = work / "checkpoint/academic-gpt-checkpoints"
    cycles_path = db_root / "cycles.sqlite"
    gateway_path = db_root / "gateway.sqlite"
    with (
        closing(_readonly_db(cycles_path, work)) as cycles,
        closing(_readonly_db(gateway_path, work)) as gateway,
    ):
        stages = gateway.execute(
            "SELECT phase FROM stages WHERE session_id=?", (session_id,)
        ).fetchall()
        if len(stages) != 1:
            raise ValueError("canonical gateway session stage is missing or ambiguous")
        phase = stages[0][0]
        missing = []
        for item in base["missing_canonical_acceptance_markers"]:
            generation_str, stage = item.split(":")
            generation = int(generation_str[1:])
            confirmed = stage == "diagnosis" and _verified_sqlite_diagnosis(
                cycles, gateway, session_id, generation
            )
            missing.append(
                {
                    "marker": item,
                    "status": ("CORROBORATED_CANONICAL_SQLITE_ONLY" if confirmed else "UNRESOLVED"),
                    "original_auxiliary_log_restored": False,
                    "provider_attested": False,
                }
            )
    completed = base["completed_generations"]
    requested = base["requested_generations"]
    if completed == requested and base["status"] == "COMPLETED" and phase == "COMPLETED":
        gate = "NOOP_COMPLETED"
    elif (
        completed < requested
        and base["status"] == "AWAITING_PROVIDER"
        and phase in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS")
    ):
        gate = "REQUIRES_AUTHENTICATED_MODEL_DECISION"
    else:
        gate = "BLOCKED_CHECKPOINT_UNCERTAIN"
    return {
        **base,
        "schema": "python-mcp-checkpoint-reconciliation-v1",
        "missing_marker_corroboration": missing,
        "checkpoint_phase": phase,
        "resume_gate": gate,
        "new_generations": 0,
        "reconciliation_mode": "READ_ONLY_NO_PROVIDER_ATTESTATION",
        "provider_invocation_independently_verified": False,
    }
