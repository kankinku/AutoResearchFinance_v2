"""Read-only evidence and SDK-log audit of isolated non-PIT model research.

Checks self-consistency, not independent provider attestation, PIT or OOS.
Never changes session state and never infers provider calls from SDK IDs alone.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash

_ID = re.compile(r"[0-9a-f]{32}\Z")


def audit_python_mcp_cohort(root: Path, work_dir: Path) -> dict[str, Any]:
    """Return a compact, unprivileged and explicitly non-attested report."""
    repo = root.resolve(strict=True)
    work = work_dir.resolve(strict=True)
    if not work.is_relative_to(repo / "state/python-mcp"):
        raise ValueError("study must remain inside the isolated fork state/python-mcp")
    for name in ("session.json", "model-audit.jsonl"):
        if (work / name).is_symlink():
            raise ValueError("study symlinks cannot be audited as immutable evidence")
    info = json.loads((work / "session.json").read_text(encoding="utf-8"))
    sid = info.get("session_id")
    if not isinstance(sid, str) or not _ID.fullmatch(sid):
        raise ValueError("invalid session identity")
    if info.get("scope") != "REAL_MODEL_NON_PIT_UNATTESTED_EXPERIMENT_ONLY":
        raise ValueError("not the explicit unverified development study scope")
    source = work / "qqq-development-nonpit-2020-2025.parquet"
    if not source.is_file() or source.is_symlink():
        raise ValueError("missing or symlinked immutable development Parquet")
    expected_source_hash = info.get("dataset_sha256")
    if (
        not isinstance(expected_source_hash, str)
        or not re.fullmatch("[a-f0-9]{64}", expected_source_hash)
        or hashlib.sha256(source.read_bytes()).hexdigest() != expected_source_hash
    ):
        raise ValueError("source data hash does not match the pinned research session")
    dataset = ParquetDataProvider.read(source)
    if (
        dataset.zone is not DataZone.DEVELOPMENT
        or dataset.timeframe != "1d"
        or not dataset.bars
        or {bar.symbol for bar in dataset.bars} != {"QQQ"}
    ):
        raise ValueError("experiment data cannot be promoted outside QQQ development zone")
    dbfile = work / "checkpoint/academic-gpt-checkpoints/cycles.sqlite"
    if not dbfile.is_file() or dbfile.is_symlink():
        raise ValueError("missing or symlinked canonical generation ledger")
    with sqlite3.connect(dbfile.resolve().as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT requested,completed,status,dataset_hash FROM sessions WHERE id=?",
            (sid,),
        ).fetchone()
        if row is None:
            raise ValueError("no matching canonical session")
        requested, completed, status, dataset_hash = row
        records = db.execute(
            "SELECT generation,evidence_json,evidence_hash FROM generations "
            "WHERE session_id=? ORDER BY generation",
            (sid,),
        ).fetchall()
    if not (
        type(completed) is int
        and type(requested) is int
        and 0 <= completed <= requested
        and len(records) == completed
    ):
        raise ValueError("canonical generation count mismatch")
    if dataset_hash is None or not re.fullmatch("[a-f0-9]{64}", dataset_hash):
        raise ValueError("canonical dataset hash missing")
    if dataset_hash != dataset.dataset_hash:
        raise ValueError("canonical session data hash differs from pinned Parquet")
    previous: str | None = None
    measured = []
    for i, (generation, raw, digest) in enumerate(records, 1):
        ev = json.loads(raw)
        expected = content_hash(
            {
                "schema": "external-gpt-academic-generation-v1",
                "session_id": sid,
                "generation": i,
                "previous_hash": previous,
                "payload": ev,
            }
        )
        if generation != i or digest != expected or ev.get("previous_evidence_hash") != previous:
            raise ValueError("canonical linked evidence hash mismatch")
        if ev.get("dataset_hash") != dataset_hash:
            raise ValueError("strategy generation switched development data")
        if (
            ev.get("broker_executable") is not False
            or ev.get("independent_oos_approved") is not False
        ):
            raise ValueError("unsafe or unsealed evidence in research cohort")
        m = ev["metrics"]
        ret, mdd, trades = m["total_return"], m["max_drawdown"], m["trade_count"]
        if (
            not isinstance(ret, (float, int))
            or isinstance(ret, bool)
            or not math.isfinite(ret)
            or not isinstance(mdd, (float, int))
            or not 0 <= mdd <= 1
            or type(trades) is not int
            or trades < 0
        ):
            raise ValueError("invalid metric record")
        measured.append(
            {
                "generation": i,
                "total_return": float(ret),
                "max_drawdown": float(mdd),
                "trade_count": trades,
            }
        )
        previous = digest
    events = []
    with (work / "model-audit.jsonl").open(encoding="utf-8") as stream:
        for _number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("model audit event is not an object")
            events.append(record)
    observations: dict[tuple[int, str], int] = Counter()
    acceptance: dict[tuple[int, str], int] = Counter()
    turns = set()
    tokens = 0
    for event in events:
        kind = event.get("event")
        stage = event.get("stage")
        g = event.get("generation")
        if kind not in ("MODEL_OUTPUT", "CANONICAL_ACCEPTED"):
            continue
        if type(g) is not int or not 1 <= g <= completed or stage not in ("plan", "diagnosis"):
            raise ValueError("model audit event targets an invalid generation or stage")
        key = (g, stage)
        if kind == "CANONICAL_ACCEPTED":
            acceptance[key] += 1
            continue
        meta = event.get("model_metadata")
        if not isinstance(meta, dict) or meta.get("host") != "Codex SDK":
            raise ValueError("recorded output lacks Codex SDK metadata")
        if (
            meta.get("independent_model_invocation_verified") is not False
            or meta.get("auth_provenance") != "UNVERIFIED_LOCAL_SDK_METADATA"
        ):
            raise ValueError("SDK event misrepresents independent provider attestation")
        turn = meta.get("turn_id")
        if not isinstance(turn, str) or not turn or turn in turns:
            raise ValueError("duplicate or missing SDK turn identifier")
        usage = meta.get("token_usage")
        count = usage.get("total_tokens") if isinstance(usage, dict) else None
        if type(count) is not int or count <= 0:
            raise ValueError("invalid SDK self-reported token count")
        tokens += count
        turns.add(turn)
        observations[key] += 1
    missing_model = [
        f"G{i}:{stage}"
        for i in range(1, completed + 1)
        for stage in ("plan", "diagnosis")
        if observations[(i, stage)] == 0
    ]
    if missing_model:
        raise ValueError("missing recorded model output for " + ",".join(missing_model))
    missing_ack = [
        f"G{i}:{stage}"
        for i in range(1, completed + 1)
        for stage in ("plan", "diagnosis")
        if acceptance[(i, stage)] == 0
    ]
    eligible = [r for r in measured if r["trade_count"] >= 30]
    best = max(eligible, key=lambda r: r["total_return"]) if eligible else None
    highest = max(measured, key=lambda r: r["total_return"]) if measured else None
    return {
        "schema": "python-mcp-development-cohort-readonly-audit-v1",
        "session_id_prefix": sid[:8],
        "status": status,
        "completed_generations": completed,
        "requested_generations": requested,
        "linked_evidence_verified": True,
        "dataset_hash": dataset_hash,
        "data_scope": "NON_PIT_DEVELOPMENT_ONLY",
        "model_sdk_output_events": sum(observations.values()),
        "sdk_self_reported_tokens": tokens,
        "missing_canonical_acceptance_markers": missing_ack,
        "max_return_generation": highest["generation"] if highest else None,
        "max_return": highest["total_return"] if highest else None,
        "best_30_trade_generation": best["generation"] if best else None,
        "best_30_trade_return": best["total_return"] if best else None,
        "best_30_trade_mdd": best["max_drawdown"] if best else None,
        "last_generation": measured[-1] if measured else None,
        "positive_generations": sum(r["total_return"] > 0 for r in measured),
        "provider_invocation_independently_verified": False,
        "independent_oos_approved": False,
        "orders_enabled": False,
    }
