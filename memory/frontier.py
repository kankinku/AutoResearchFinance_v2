from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CandidateState(str, Enum):
    CRASH = "CRASH"
    REJECT = "REJECT"
    NEAR_MISS = "NEAR_MISS"
    SURVIVOR = "SURVIVOR"
    FRONTIER = "FRONTIER"
    CHAMPION_CANDIDATE = "CHAMPION_CANDIDATE"
    CHAMPION = "CHAMPION"


class StateTransitionError(ValueError):
    """Raised when a candidate state transition is not permitted."""


_ALLOWED_TRANSITIONS = {
    CandidateState.CRASH: {CandidateState.REJECT, CandidateState.NEAR_MISS},
    CandidateState.REJECT: set(),
    CandidateState.NEAR_MISS: {CandidateState.SURVIVOR, CandidateState.REJECT},
    CandidateState.SURVIVOR: {
        CandidateState.FRONTIER,
        CandidateState.NEAR_MISS,
        CandidateState.REJECT,
    },
    CandidateState.FRONTIER: {CandidateState.CHAMPION_CANDIDATE, CandidateState.REJECT},
    CandidateState.CHAMPION_CANDIDATE: {CandidateState.CHAMPION, CandidateState.REJECT},
    CandidateState.CHAMPION: set(),
}


def transition(current: CandidateState, target: CandidateState) -> CandidateState:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise StateTransitionError(f"illegal state transition: {current.value} -> {target.value}")
    return target


@dataclass(frozen=True)
class CandidateRecord:
    candidate_hash: str
    family: str
    score: float
    status: CandidateState


class Frontier:
    def __init__(self) -> None:
        self._by_family: dict[str, CandidateRecord] = {}

    def consider(self, record: CandidateRecord) -> bool:
        if record.status not in {
            CandidateState.SURVIVOR,
            CandidateState.FRONTIER,
            CandidateState.CHAMPION_CANDIDATE,
            CandidateState.CHAMPION,
        }:
            return False
        current = self._by_family.get(record.family)
        if current is not None and current.score >= record.score:
            return False
        self._by_family[record.family] = record
        return True

    def get(self, family: str) -> CandidateRecord:
        return self._by_family[family]

    def records(self) -> tuple[CandidateRecord, ...]:
        return tuple(self._by_family[key] for key in sorted(self._by_family))
