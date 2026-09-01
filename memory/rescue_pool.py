from __future__ import annotations

from dataclasses import dataclass

from memory.frontier import CandidateState


@dataclass(frozen=True)
class RescueEntry:
    candidate_hash: str
    parent_hash: str
    mutations: tuple[str, ...]
    failure_reason: str
    family: str


class RescuePool:
    def __init__(self) -> None:
        self._entries: dict[str, RescueEntry] = {}

    def add(self, entry: RescueEntry, *, status: CandidateState) -> None:
        if status is not CandidateState.NEAR_MISS:
            raise ValueError("Rescue Pool accepts only NEAR_MISS candidates")
        self._entries.setdefault(entry.candidate_hash, entry)

    def entries(self) -> tuple[RescueEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))
