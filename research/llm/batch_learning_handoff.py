"""Evidence-verified, read-only batch findings for the *existing* GPT research loop.

A fast deterministic batch is NOT a GPT generation. Even the best failed
candidate is an analysis hint, never an approved parent, OOS result or strategy.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore


def _empty(status: str) -> dict[str, Any]:
    return {
        "schema": "batch-learning-handoff-v1",
        "status": status,
        "batches": [],
        "candidate_promotion_authorized": False,
        "per_generation_llm_evolution_verified": False,
        "independent_oos_approved": False,
        "orders_enabled": False,
        "instruction": (
            "These are historical, non-PIT development observations for GPT hypothesis "
            "generation only. Do not inherit rejected strategies, alter validation gates, "
            "or count batch evaluations as GPT-authored generations."
        ),
    }


def _finite_number(item: object) -> float | None:
    if isinstance(item, (float, int)) and not isinstance(item, bool) and math.isfinite(item):
        return float(item)
    return None


def _verify_batch(
    row: sqlite3.Row, hist: list[sqlite3.Row], events: list[dict[str, Any]]
) -> dict[str, Any]:
    requested, completed = int(row["requested"]), int(row["completed"])
    if (
        not 0 < completed <= requested
        or len(hist) != completed
        or [h["generation"] for h in hist] != list(range(1, completed + 1))
    ):
        raise EvidenceIntegrityError("bounded batch generation counter mismatch")
    kinds: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        kinds.setdefault(ev["kind"], []).append(ev["payload"])
    runs, ends, manifests = kinds.get("run", []), kinds.get("end", []), kinds.get("manifest", [])
    if len(runs) != 1 or len(ends) != 1 or len(manifests) != 1 or ends[0]["status"] != "COMPLETED":
        raise EvidenceIntegrityError("batch has incomplete run evidence")
    if (
        runs[0].get("settings", {}).get("job_id") != row["id"]
        or runs[0].get("requested_generations") != requested
    ):
        raise EvidenceIntegrityError("batch identity mismatch")
    manifest = manifests[0]
    if manifest.get("data_zone") != "development" or not isinstance(
        manifest.get("dataset_hash"), str
    ):
        raise EvidenceIntegrityError("non-development batch cannot be shared")
    generation_events = kinds.get("generation", [])
    if len(generation_events) != completed:
        raise EvidenceIntegrityError("batch is missing generation evidence")
    per_generation = {g.get("generation"): g for g in generation_events}
    if set(per_generation) != set(range(1, completed + 1)):
        raise EvidenceIntegrityError("generation identities are invalid")
    attempts = kinds.get("attempt", [])
    by_id = {a.get("attempt_id"): a for a in attempts}
    if len(by_id) != len(attempts):
        raise EvidenceIntegrityError("duplicate attempt identities")
    counted = set()
    failures: Counter[str] = Counter()
    best: dict[str, Any] | None = None
    evaluated = rejected = skipped = 0
    for h in hist:
        g = per_generation[h["generation"]]
        counts = json.loads(h["result_counts"])
        if (
            not isinstance(counts, dict)
            or g["status"] != h["result_status"]
            or g["generation"] != h["generation"]
        ):
            raise EvidenceIntegrityError("generation history and evidence disagree")
        dup = counts.get("DUPLICATE_SKIPPED")
        if type(dup) is not int or dup < 0 or dup != g.get("duplicate_skipped"):
            raise EvidenceIntegrityError("duplicate counts disagree")
        skipped += dup
        identifier = g.get("attempt_id")
        if identifier is None:
            if h["result_status"] != "NO_NEW_CANDIDATES" or h["candidate_count"] != 0:
                raise EvidenceIntegrityError("missing generation attempt")
            continue
        attempt = by_id.get(identifier)
        if (
            not attempt
            or identifier in counted
            or attempt.get("generation") != h["generation"]
            or attempt.get("status") != "COMPLETED"
        ):
            raise EvidenceIntegrityError("attempt identity mismatch")
        counted.add(identifier)
        candidates = attempt.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != h["candidate_count"]:
            raise EvidenceIntegrityError("candidate count mismatch")
        for c in candidates:
            if c.get("dataset_hash") != manifest["dataset_hash"] or c.get("status") not in {
                "REJECT",
                "SURVIVOR",
                "FRONTIER",
                "CHAMPION_CANDIDATE",
                "CHAMPION",
            }:
                raise EvidenceIntegrityError("candidate evidence identity mismatch")
            evaluated += 1
            if c["status"] != "REJECT":
                continue
            rejected += 1
            gates = c.get("failed_gates", [])
            if not isinstance(gates, list) or not all(isinstance(x, str) for x in gates):
                raise EvidenceIntegrityError("invalid failure evidence")
            failures.update(sorted(set(gates)))
            cagr = _finite_number(c.get("full_cagr"))
            if cagr is not None and (best is None or cagr > best["cagr"]):
                best = {
                    "cagr": cagr,
                    "mdd": _finite_number(c.get("max_drawdown")),
                    "trades": c.get("trade_count") if type(c.get("trade_count")) is int else None,
                    "failed_gates": sorted(set(gates)),
                    "candidate_hash": c["candidate_hash"],
                }
    if (
        len(counted) != len(attempts)
        or evaluated != sum(h["candidate_count"] for h in hist)
        or rejected != sum(json.loads(h["result_counts"]).get("REJECT", 0) for h in hist)
    ):
        raise EvidenceIntegrityError("uncommitted or miscounted candidate evidence")
    return {
        "job_id": row["id"],
        "research_run_id": row["research_run_id"],
        "source": "IMMUTABLE_VERIFIED_BATCH_EVIDENCE",
        "research_type": "FIXED_INTENT_LOCAL_WORKER_NOT_GPT_GENERATIONS",
        "completed": completed,
        "requested": requested,
        "evaluated": evaluated,
        "duplicates_skipped": skipped,
        "rejected": rejected,
        "top_failure_gates": [
            {"gate": name, "count": n}
            for name, n in sorted(failures.items(), key=lambda item: (-item[1], item[0]))[:4]
        ],
        "best_rejected_research_hint": best,
        "dataset_hash": manifest["dataset_hash"],
        "point_in_time_verified": manifest.get("market_data_quality", {}).get(
            "point_in_time_verified"
        )
        is True,
        "independent_oos_measured": False,
    }


def recent_batch_learning(state_dir: Path, *, limit: int = 2) -> dict[str, Any]:
    """Provide small trustworthy model guidance, never edit operational state.

    Read only fully completed batch + immutable Evidence. On any inconsistency
    return an explicit blocker, rather than leaking partially verified hints.
    """
    if not 1 <= limit <= 3:
        raise ValueError("bounded learning history supports 1–3 batches")
    path = state_dir / "system" / "gpt-research-batches.sqlite"
    if not path.is_file():
        return _empty("NO_BOUNDED_BATCHES")
    try:
        with closing(
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
        ) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            rows = conn.execute(
                "SELECT id,research_run_id,requested,completed,status FROM batches "
                "WHERE status='COMPLETED' ORDER BY created DESC,id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            history = {
                r["id"]: conn.execute(
                    "SELECT * FROM generation_history WHERE batch_id=? ORDER BY generation",
                    (r["id"],),
                ).fetchall()
                for r in rows
            }
        if not rows:
            return _empty("NO_COMPLETED_BATCHES")
        events = EvidenceStore(state_dir).events()
        by_run: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_run.setdefault(e["payload"]["research_run_id"], []).append(e)
        out = []
        for row in rows:
            run = row["research_run_id"]
            if not isinstance(run, str) or len(run) != 32:
                raise EvidenceIntegrityError("missing research run identity")
            out.append(_verify_batch(row, history[row["id"]], by_run.get(run, [])))
        return {**_empty("VERIFIED_DEVELOPMENT_MEMORY"), "batches": out}
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, EvidenceIntegrityError):
        return _empty("EVIDENCE_UNVERIFIED")
