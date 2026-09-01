from __future__ import annotations

from typing import Any

from core.integrity.audit import AuditLog
from evaluation.selector import FunnelResult
from memory.state_files import StateFileStore


def promote_candidate(
    result: FunnelResult, *, store: StateFileStore, audit: AuditLog, actor: str
) -> dict[str, Any]:
    if result.status != "SURVIVOR":
        raise PermissionError("only SURVIVOR candidates can be promoted")
    if not actor:
        raise PermissionError("promotion actor is required")
    current: dict[str, Any] | None = None
    try:
        current = store.read("champion").payload.get("champion")
    except FileNotFoundError:
        pass
    if isinstance(current, dict) and float(current.get("score", float("-inf"))) >= result.score:
        raise ValueError("candidate does not improve current champion")
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "status": "CHAMPION",
        "champion_hash": result.candidate_hash,
        "family": result.family,
        "score": result.score,
        "gates": [gate.name for gate in result.gates],
    }
    store.write("champion", {**snapshot, "champion": snapshot})
    audit.append(
        "promote_champion",
        actor=actor,
        inputs={"candidate_hash": result.candidate_hash, "score": result.score},
    )
    return snapshot
