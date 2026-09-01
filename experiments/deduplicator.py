from __future__ import annotations

from dataclasses import dataclass

from experiments.candidate_generator import Candidate


@dataclass(frozen=True)
class DeduplicationResult:
    unique: tuple[Candidate, ...]
    duplicate_hashes: tuple[str, ...]


def deduplicate_candidates(candidates: list[Candidate]) -> DeduplicationResult:
    unique: list[Candidate] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for candidate in candidates:
        if candidate.candidate_hash in seen:
            if candidate.candidate_hash not in duplicates:
                duplicates.append(candidate.candidate_hash)
            continue
        seen.add(candidate.candidate_hash)
        unique.append(candidate)
    return DeduplicationResult(tuple(unique), tuple(duplicates))
