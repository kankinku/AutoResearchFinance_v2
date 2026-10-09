"""Read-only frontier reconstruction from checksum-verified immutable attempts."""

from __future__ import annotations

from math import isfinite
from pathlib import Path

from memory.evidence_store import EvidenceStore
from memory.frontier import CandidateRecord, CandidateState, Frontier
from strategy_ir.schema import StrategyIR


def frontier_summary(state_dir: Path) -> list[dict[str, str | float]]:
    frontier = Frontier()
    for event in EvidenceStore(state_dir).events():
        if event["kind"] != "attempt":
            continue
        for candidate in event["payload"]["candidates"]:
            status = candidate.get("status")
            if status not in {"SURVIVOR", "FRONTIER", "CHAMPION_CANDIDATE", "CHAMPION"}:
                continue
            candidate_hash, family, score = (
                candidate.get("candidate_hash"),
                candidate.get("family"),
                candidate.get("score"),
            )
            if (
                not isinstance(candidate_hash, str)
                or not isinstance(family, str)
                or type(score) not in {float, int}
                or not isfinite(score)
            ):
                continue
            frontier.consider(
                CandidateRecord(candidate_hash, family, float(score), CandidateState(status))
            )
    return [
        {
            "candidate_hash": record.candidate_hash,
            "family": record.family,
            "score": record.score,
            "status": record.status.value,
        }
        for record in sorted(
            frontier.records(), key=lambda item: (-item.score, item.candidate_hash)
        )
    ]


def frontier_parents(
    state_dir: Path, *, research_run_id: str | None = None
) -> tuple[StrategyIR, ...]:
    """Load only eligible, hash-matched executable parents from immutable Evidence.

    Legacy attempts without IR snapshots remain readable but cannot be used as
    replayable parents; a hash mismatch must never be silently repaired.
    """
    from pydantic import ValidationError

    from core.integrity.hashes import content_hash

    scoped_attempts = [
        event
        for event in EvidenceStore(state_dir).events()
        if event["kind"] == "attempt"
        and (research_run_id is None or event["payload"]["research_run_id"] == research_run_id)
    ]
    frontier = Frontier()
    for event in scoped_attempts:
        for candidate in event["payload"]["candidates"]:
            status = candidate.get("status")
            if status not in {"SURVIVOR", "FRONTIER", "CHAMPION_CANDIDATE", "CHAMPION"}:
                continue
            candidate_hash, family, score = (
                candidate.get("candidate_hash"),
                candidate.get("family"),
                candidate.get("score"),
            )
            if (
                not isinstance(candidate_hash, str)
                or not isinstance(family, str)
                or type(score) not in {int, float}
                or not isfinite(score)
            ):
                continue
            frontier.consider(
                CandidateRecord(candidate_hash, family, float(score), CandidateState(status))
            )
    selected = sorted(frontier.records(), key=lambda item: (-item.score, item.candidate_hash))
    best_by_hash = {item.candidate_hash for item in selected}
    restored: dict[str, StrategyIR] = {}
    for event in scoped_attempts:
        for candidate in event["payload"]["candidates"]:
            identifier = candidate.get("candidate_hash")
            if identifier not in best_by_hash:
                continue
            if candidate.get("status") not in {
                "SURVIVOR",
                "FRONTIER",
                "CHAMPION_CANDIDATE",
                "CHAMPION",
            }:
                continue
            raw = candidate.get("strategy_ir")
            declared_hash = candidate.get("strategy_ir_hash")
            if not isinstance(raw, dict) or not isinstance(declared_hash, str):
                continue
            if content_hash(raw) != declared_hash:
                continue
            try:
                strategy = StrategyIR.model_validate(raw)
            except ValidationError:
                continue
            restored[str(identifier)] = strategy
    return tuple(
        restored[identifier]
        for identifier in (item.candidate_hash for item in selected)
        if identifier in restored
    )
