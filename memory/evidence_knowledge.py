"""Recoverable Knowledge projection; only constructed evidence reaches the LLM."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from memory.evidence_store import EvidenceIntegrityError, EvidenceStore, digest, encode


def sync_knowledge(state_dir: Path) -> None:
    store = EvidenceStore(state_dir)
    if not store.path.exists():
        return
    # Serialize projections with writers. The journal remains canonical after a crash
    # between its commit and this replace; the next context read repeats this projection.
    try:
        with sqlite3.connect(store.path, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            events = store.events()
            target = state_dir / "knowledge.json"
            previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
            if not isinstance(previous, dict):
                raise EvidenceIntegrityError("invalid knowledge object")
            payload = dict(previous)
            payload.setdefault("schema_version", 1)
            for name in ("known_good", "known_bad", "unexplored"):
                if not isinstance(payload.setdefault(name, []), list):
                    raise EvidenceIntegrityError("invalid knowledge category")
                payload[name] = list(payload[name])
            ids = {
                item.get("experiment_id")
                for name in ("known_good", "known_bad", "unexplored")
                for item in payload[name]
                if isinstance(item, dict)
            }
            keys = {
                e["payload"]["research_run_id"]: e["payload"]["comparison_key"]
                for e in events
                if e["kind"] == "manifest"
            }
            for event in events:
                if event["kind"] != "attempt":
                    continue
                attempt = event["payload"]
                for index, candidate in enumerate(attempt.get("candidates", [])):
                    experiment_id = digest(
                        [
                            attempt["research_run_id"],
                            attempt["attempt_id"],
                            index,
                            candidate["candidate_hash"],
                        ]
                    )
                    if experiment_id in ids:
                        continue
                    category = {
                        "REJECT": "known_bad",
                        "NEAR_MISS": "unexplored",
                        "SURVIVOR": "known_good",
                        "FRONTIER": "known_good",
                    }.get(candidate["status"])
                    if category is None:
                        continue
                    payload[category].append(
                        {
                            **candidate,
                            "experiment_id": experiment_id,
                            "research_run_id": attempt["research_run_id"],
                            "attempt_id": attempt["attempt_id"],
                            "generation": attempt["generation"],
                            "comparison_key": keys.get(attempt["research_run_id"]),
                        }
                    )
                    ids.add(experiment_id)
            if payload == previous:
                return
            temporary: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=state_dir, prefix=".knowledge-", delete=False
                ) as handle:
                    temporary = handle.name
                    handle.write(encode(payload) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None and Path(temporary).exists():
                    Path(temporary).unlink()
    except (sqlite3.Error, json.JSONDecodeError, OSError) as exc:
        raise EvidenceIntegrityError("knowledge projection failed") from exc


def failure_context(state_dir: Path, max_items: int = 20) -> list[dict[str, Any]]:
    if max_items < 1:
        raise ValueError("max_items must be positive")
    sync_knowledge(state_dir)
    # Use verified journal fields instead of exposing arbitrary legacy Knowledge fields.
    events = EvidenceStore(state_dir).events()
    keys = {
        e["payload"]["research_run_id"]: e["payload"]["comparison_key"]
        for e in events
        if e["kind"] == "manifest"
    }
    groups: dict[str, dict[str, Any]] = {}
    for event in reversed(events):
        if event["kind"] != "attempt":
            continue
        attempt = event["payload"]
        for row in attempt.get("candidates", []):
            if row["status"] != "REJECT":
                continue
            comparison_key = keys.get(attempt["research_run_id"])
            signature = digest([comparison_key, row["candidate_hash"], sorted(row["failed_gates"])])
            if signature in groups:
                groups[signature]["occurrences"] += 1
                continue
            groups[signature] = {
                "candidate_hash": row["candidate_hash"],
                "family": row["family"],
                "failed_gates": row["failed_gates"],
                "causal_status": "UNKNOWN",
                "generation": attempt["generation"],
                "comparison_key": comparison_key,
                "occurrences": 1,
            }
    # Insertion order is latest occurrence first; repetition counts include the full journal.
    return list(groups.values())[:max_items]
