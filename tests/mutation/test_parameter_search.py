from __future__ import annotations

from mutation.parameter import (
    BayesianObservation,
    ParameterDomain,
    bayesian_search,
    grid_search,
    random_search,
)


def domains() -> tuple[ParameterDomain, ...]:
    return (
        ParameterDomain("fast", (5, 10, 15)),
        ParameterDomain("slow", (20, 30)),
    )


def test_grid_search_returns_cartesian_product() -> None:
    result = grid_search(domains())

    assert len(result) == 6
    assert result[0] == {"fast": 5, "slow": 20}
    assert result[-1] == {"fast": 15, "slow": 30}


def test_random_search_is_seeded_and_bounded() -> None:
    first = random_search(domains(), count=4, seed=11)
    second = random_search(domains(), count=4, seed=11)

    assert first == second
    assert len(first) == 4
    assert all(point["fast"] in {5, 10, 15} for point in first)
    assert all(point["slow"] in {20, 30} for point in first)


def test_bayesian_search_is_seeded_and_uses_observed_scores() -> None:
    observations = [
        BayesianObservation({"fast": 10, "slow": 30}, 0.9),
        BayesianObservation({"fast": 5, "slow": 20}, 0.1),
    ]

    first = bayesian_search(domains(), observations, count=3, seed=7)
    second = bayesian_search(domains(), observations, count=3, seed=7)

    assert first == second
    assert len(first) == 3
    assert all(point in grid_search(domains()) for point in first)
    assert first[0] == {"fast": 10, "slow": 30}


def test_random_search_never_repeats_combinations_when_budget_exceeds_space() -> None:
    tiny = (ParameterDomain("fast", (5, 10)),)
    first = random_search(tiny, count=8, seed=42)
    second = random_search(tiny, count=8, seed=42)

    assert first == second
    assert len(first) == 2
    assert {point["fast"] for point in first} == {5, 10}


def test_random_search_deduplicates_repeated_parameter_domain_values() -> None:
    repeated = (ParameterDomain("fast", (5, 5, 10)),)
    result = random_search(repeated, count=3, seed=42)
    assert len(result) == 2
    assert {point["fast"] for point in result} == {5, 10}


def test_empty_parameter_search_space_produces_one_unique_baseline() -> None:
    assert random_search((), count=8, seed=42) == [{}]
    assert random_search((), count=0, seed=42) == []
