from __future__ import annotations

from memory.frontier import CandidateRecord, CandidateState, Frontier
from orchestration.policies import allocate_sources


def test_policy_allocation_is_deterministic_and_covers_all_sources() -> None:
    frontier = Frontier()
    frontier.consider(CandidateRecord("m", "momentum", 0.7, CandidateState.FRONTIER))
    frontier.consider(CandidateRecord("b", "breakout", 0.6, CandidateState.FRONTIER))

    first = allocate_sources(frontier, candidate_target=10, seed=3)
    second = allocate_sources(frontier, candidate_target=10, seed=3)

    assert first == second
    assert sum(first.values()) == 10
    assert set(first) == {"exploit", "explore", "crossover", "rescue"}
