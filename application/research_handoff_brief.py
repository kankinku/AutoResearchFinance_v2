"""Minimal read-only resume locator backed by canonical on-disk research state.

No chat history, cookies, background model calls, fresh generations or new MCP tools.
The full checkpoint is still read on demand through get_algorithm_research.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from application.academic_checkpoint_service import AcademicMCPCheckpointService

_ID = re.compile(r"[0-9a-f]{32}\Z")
_PENDING = frozenset({"AWAITING_PLAN", "AWAITING_DIAGNOSIS"})
_ACTIVE = _PENDING | {"RUNNING", "INTERRUPTED"}

_ACTION = {
    "AWAITING_PLAN": "AUTHOR_AND_SUBMIT_PLAN",
    "AWAITING_DIAGNOSIS": "AUTHOR_AND_SUBMIT_DIAGNOSIS",
    "RUNNING": "STOP_AND_VERIFY_RUNNING_WORKER",
    "INTERRUPTED": "EXPLICIT_RECONCILIATION_AFTER_WORKER_STOP",
}


def _read_db(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError("research checkpoint database is not mounted")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def research_handoff_brief(*, root: Path, state_dir: Path) -> dict[str, Any]:
    """Find an active session when the calling GPT has forgotten its ID.

    Treat missing DBs, ambiguous sessions and broken evidence as distinct states.
    Never expose any checkpoint token through the general overview.
    """
    base = state_dir / "academic-gpt-checkpoints"
    gateway_file = base / "gateway.sqlite"
    cycles_file = base / "cycles.sqlite"
    empty: dict[str, Any] = {
        "schema": "quant-cross-chat-research-handoff-v1",
        "status": "NO_ACTIVE_RESEARCH",
        "active_count": 0,
        "selected_session_id": None,
        "next_read": None,
        "active_sessions": [],
        "recent_terminal_sessions": [],
        "orders_enabled": False,
        "independent_oos_approved": False,
        "chat_memory_is_not_source_of_truth": True,
        "automatic_model_calls_started": 0,
    }
    if not gateway_file.exists() and not cycles_file.exists():
        return empty
    if not gateway_file.exists() or not cycles_file.exists():
        raise ValueError("research checkpoint database pair is incomplete")

    with _read_db(gateway_file) as gateway, _read_db(cycles_file) as cycles:
        rows = gateway.execute(
            "SELECT session_id, phase FROM stages ORDER BY rowid DESC LIMIT 256"
        ).fetchall()
        active = []
        terminal = []
        for row in rows:
            session_id, phase = row["session_id"], row["phase"]
            if not isinstance(session_id, str) or _ID.fullmatch(session_id) is None:
                raise ValueError("research checkpoint session identity invalid")
            canonical = cycles.execute(
                "SELECT requested, completed, status, dataset_hash FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if canonical is None:
                raise ValueError("research checkpoint session missing from canonical ledger")
            requested, completed, status = (
                canonical["requested"],
                canonical["completed"],
                canonical["status"],
            )
            if (
                type(requested) is not int
                or type(completed) is not int
                or not 0 <= completed <= requested <= 100
                or phase not in _ACTIVE | {"CANCELLED", "COMPLETED"}
            ):
                raise ValueError("research checkpoint status or progress invalid")
            if phase in {"CANCELLED", "COMPLETED"}:
                terminal.append(
                    {
                        "session_id": session_id,
                        "checkpoint_phase": phase,
                        "completed_generations": completed,
                        "requested_generations": requested,
                    }
                )
            if phase in _ACTIVE:
                if status not in {"AWAITING_PROVIDER", "RUNNING", "INTERRUPTED"}:
                    raise ValueError("gateway and canonical research lifecycle disagree")
                active.append(
                    {
                        "session_id": session_id,
                        "checkpoint_phase": phase,
                        "completed_generations": completed,
                        "requested_generations": requested,
                        "dataset_hash": canonical["dataset_hash"],
                    }
                )
        if len(rows) == 256:
            raise ValueError("research session discovery is capped; review exact sessions")
        if not active:
            return {**empty, "recent_terminal_sessions": terminal[:2]}
        head = {
            **empty,
            "active_count": len(active),
            "recent_terminal_sessions": terminal[:2],
            "active_sessions": active[:8],
            "active_sessions_truncated": len(active) > 8,
        }
        if len(active) != 1:
            return {
                **head,
                "status": "SELECTION_REQUIRED",
                "message": (
                    "Choose an exact session_id; never merge contexts "
                    "from different live research sessions."
                ),
            }

        selected = active[0]
        sid = selected["session_id"]
        read = {
            "tool": "get_algorithm_research",
            "session_id": sid,
            "response_mode": "compact",
        }
        if selected["checkpoint_phase"] not in _PENDING:
            return {
                **head,
                "status": "OPERATOR_RECOVERY_REQUIRED",
                "selected_session_id": sid,
                "checkpoint_phase": selected["checkpoint_phase"],
                "completed_generations": selected["completed_generations"],
                "requested_generations": selected["requested_generations"],
                "next_checkpoint_action": _ACTION[selected["checkpoint_phase"]],
                "next_read": read,
                "message": (
                    "Do not retry or reconcile until the old research worker is confirmed stopped."
                ),
            }

    snapshot = AcademicMCPCheckpointService(project_root=root, state_dir=state_dir).get(
        {"session_id": sid}
    )
    if (
        snapshot.get("orders_enabled") is not False
        or snapshot.get("independent_oos_approved") is not False
    ):
        raise ValueError("unsafe research checkpoint privileges")
    if (
        snapshot.get("checkpoint_phase") != selected["checkpoint_phase"]
        or snapshot.get("completed_generations") != selected["completed_generations"]
        or snapshot.get("requested_generations") != selected["requested_generations"]
    ):
        raise ValueError("research checkpoint changed while preparing the handoff")

    history = snapshot["history"]
    if len(history) != selected["completed_generations"]:
        raise ValueError("research checkpoint evidence count does not match")
    recent = [
        {
            "generation": item["generation"],
            "evidence_hash": item["evidence_hash"],
            "metrics": {
                key: item["metrics"][key]
                for key in ("total_return", "max_drawdown", "trade_count", "sharpe")
            },
        }
        for item in history[-3:]
    ]
    context = snapshot["model_context"]
    learning = context.get("experiment_learning", {})
    measured = learning.get("recent_evidence", [])
    latest_experiments = {
        "measured_count": learning.get("measured_experiment_count", 0),
        "recent_results": [
            {
                "generation": item["generation"],
                "hypothesis_id": item["hypothesis_id"],
                "status": item["status"],
                "metric": item["metric"],
                "observed_delta": item["observed_delta"],
            }
            for item in measured[-2:]
        ],
    }
    parent = context.get("selected_development_parent")
    return {
        **head,
        "status": "RESUMABLE",
        "selected_session_id": sid,
        "checkpoint_phase": selected["checkpoint_phase"],
        "completed_generations": selected["completed_generations"],
        "requested_generations": selected["requested_generations"],
        "next_generation": selected["completed_generations"] + 1,
        "next_checkpoint_action": _ACTION[selected["checkpoint_phase"]],
        "output_contract": (
            "DiagnosticResponse"
            if selected["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
            else context.get("output_contract")
        ),
        "next_read": read,
        "last_evidence_hash": history[-1]["evidence_hash"] if history else None,
        "history_sample": recent,
        "latest_experiments": latest_experiments,
        "research_direction": context.get("research_direction", {}).get("recommended_mode"),
        "selected_parent": (
            {
                "source_generation": parent.get("source_generation"),
                "strategy_hash": parent.get("successor_strategy_hash"),
            }
            if isinstance(parent, dict)
            else None
        ),
        "verified_source": "canonical_academic_checkpoint_sqlite",
        "detailed_model_context_included": False,
        "checkpoint_token_included": False,
        "next_step": (
            "Call next_read immediately before a plan or diagnosis; "
            "never reuse a stale token from another chat."
        ),
    }
