"""Read-only and source-labelled status bridge for deterministic Quant batches.

This view does NOT represent the separate GPT-authored academic checkpoint as a
continuation and does not imply 100 actual model-authored generations.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BATCH_DB_PATH = ROOT / "state/moon-http/research/system/gpt-research-batches.sqlite"


def _utc(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def batch_snapshot(path: Path = BATCH_DB_PATH) -> dict[str, Any]:
    """Read the latest persisted batch and measured generation counters only.

    Immutable source for all displayed numbers: batches and generation_history.
    A missing or corrupted source is an explicit error, never a zero-generation
    pretend result. SQLite readonly URI prevents UI-driven state mutation.
    """
    if not path.is_file():
        raise FileNotFoundError("bounded batch status database unavailable")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("""SELECT id,status,requested,completed,created,started,
            finished,heartbeat,research_run_id,error_code FROM batches
            ORDER BY created DESC,id DESC LIMIT 4""").fetchall()
        if not rows:
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "research_type": "FIXED_PARAMETER_BACKTEST_NOT_GPT_EVOLUTION",
                "orders_enabled": False,
                "batch": None,
                "recent_batches": [],
            }
        row = rows[0]
        history = db.execute(
            """SELECT generation,seconds,parent_id,successor_id,
            result_status,result_counts,candidate_count FROM generation_history
            WHERE batch_id=? ORDER BY generation""",
            (row["id"],),
        ).fetchall()
    history_out = []
    total_candidates = 0
    total_skipped = 0
    total_rejected = 0
    total_promoted = 0
    for entry in history:
        counts = json.loads(entry["result_counts"])
        if not isinstance(counts, dict):
            raise ValueError("Invalid batch result counts")
        candidates = int(entry["candidate_count"])
        skipped = int(counts.get("DUPLICATE_SKIPPED", 0))
        rejected = int(counts.get("REJECT", 0))
        promoted = sum(int(counts.get(k, 0)) for k in ("PASS", "PROMOTED", "ACCEPT"))
        total_candidates += candidates
        total_skipped += skipped
        total_rejected += rejected
        total_promoted += promoted
        history_out.append(
            {
                "generation": int(entry["generation"]),
                "candidates_evaluated": candidates,
                "duplicate_skipped": skipped,
                "rejected": rejected,
                "promoted": promoted,
                "status": entry["result_status"],
            }
        )
    expected = int(row["completed"])
    actual = [g["generation"] for g in history_out]
    consistent = actual == list(range(1, expected + 1))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_type": "FIXED_PARAMETER_BACKTEST_NOT_GPT_EVOLUTION",
        "data_scope": "DEVELOPMENT_NON_PIT_OOS_NOT_MEASURED",
        "orders_enabled": False,
        "batch": {
            "batch_id": row["id"],
            "research_run_id": row["research_run_id"],
            "status": row["status"],
            "requested": int(row["requested"]),
            "completed": expected,
            "candidates_evaluated": total_candidates,
            "duplicate_skipped": total_skipped,
            "rejected": total_rejected,
            "promoted": total_promoted,
            "checkpoints_consistent": consistent,
            "created_at": _utc(row["created"]),
            "started_at": _utc(row["started"]),
            "finished_at": _utc(row["finished"]),
            "heartbeat_at": _utc(row["heartbeat"]),
            "error_code": row["error_code"],
            "generations": history_out[-100:],
        },
        "recent_batches": [
            {
                "batch_id": r["id"],
                "status": r["status"],
                "completed": int(r["completed"]),
                "requested": int(r["requested"]),
            }
            for r in rows
        ],
    }
