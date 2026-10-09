from __future__ import annotations

from dataclasses import dataclass

from experiments.candidate_generator import Candidate
from experiments.identity import semantic_strategy_hash


@dataclass(frozen=True)
class DeduplicationResult:
    unique: tuple[Candidate, ...]
    duplicate_hashes: tuple[str, ...]


def deduplicate_candidates(
    candidates: list[Candidate], *, semantic: bool = False
) -> DeduplicationResult:
    unique: list[Candidate] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for candidate in candidates:
        identity = (
            semantic_strategy_hash(candidate.strategy) if semantic else candidate.candidate_hash
        )
        if identity in seen:
            if candidate.candidate_hash not in duplicates:
                duplicates.append(candidate.candidate_hash)
            continue
        seen.add(identity)
        unique.append(candidate)
    return DeduplicationResult(tuple(unique), tuple(duplicates))
