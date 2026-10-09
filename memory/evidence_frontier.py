"""Read-only frontier reconstruction from checksum-verified immutable attempts."""

from __future__ import annotations

from math import isfinite
from pathlib import Path

from memory.evidence_store import EvidenceStore
from memory.frontier import CandidateRecord, CandidateState, Frontier


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
