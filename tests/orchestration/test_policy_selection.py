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


def test_source_allocation_respects_configured_policy_weights() -> None:
    from pathlib import Path

    from research.policy import load_policy

    search = load_policy(Path("research/policy.yaml")).search.model_copy(
        update={
            "exploit_ratio": 0.10,
            "explore_ratio": 0.60,
            "crossover_ratio": 0.20,
            "rescue_ratio": 0.10,
        }
    )
    frontier = Frontier()
    assert allocate_sources(frontier, candidate_target=100, seed=3, policy=search) == {
        "exploit": 10,
        "explore": 60,
        "crossover": 20,
        "rescue": 10,
    }


def test_source_allocation_rejects_invalid_weights() -> None:
    import pytest

    frontier = Frontier()
    with pytest.raises(ValueError, match="sum"):
        allocate_sources(
            frontier,
            candidate_target=10,
            seed=3,
            ratios={"exploit": 0.5, "explore": 0.5, "crossover": 0.5, "rescue": 0.5},
        )
