from __future__ import annotations

import pytest

from memory.frontier import (
    CandidateRecord,
    CandidateState,
    Frontier,
    StateTransitionError,
    transition,
)


def record(
    candidate_hash: str, family: str, score: float, status: CandidateState
) -> CandidateRecord:
    return CandidateRecord(candidate_hash, family, score, status)


def test_state_machine_allows_progression_and_rejects_illegal_transition() -> None:
    assert transition(CandidateState.CRASH, CandidateState.REJECT) is CandidateState.REJECT
    assert transition(CandidateState.SURVIVOR, CandidateState.FRONTIER) is CandidateState.FRONTIER
    with pytest.raises(StateTransitionError, match="illegal"):
        transition(CandidateState.REJECT, CandidateState.CHAMPION)


def test_frontier_keeps_best_candidate_per_family() -> None:
    frontier = Frontier()

    assert frontier.consider(record("m1", "momentum", 0.7, CandidateState.SURVIVOR))
    assert frontier.consider(record("b1", "breakout", 0.5, CandidateState.SURVIVOR))
    assert frontier.consider(record("m2", "momentum", 0.8, CandidateState.FRONTIER))
    assert not frontier.consider(record("m0", "momentum", 0.6, CandidateState.SURVIVOR))
    assert frontier.get("momentum").candidate_hash == "m2"
    assert frontier.get("breakout").candidate_hash == "b1"
