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


def test_random_search_samples_huge_space_without_grid_materialization(monkeypatch) -> None:
    import mutation.parameter as parameter

    def grid_must_not_run(_domains):
        raise AssertionError("random search must not materialize cartesian product")

    monkeypatch.setattr(parameter, "grid_search", grid_must_not_run)
    huge = tuple(ParameterDomain(f"p{i}", (0, 1)) for i in range(28))
    first = random_search(huge, count=5, seed=123)
    assert len(first) == 5
    assert len({tuple(sorted(point.items())) for point in first}) == 5
    assert first == random_search(huge, count=5, seed=123)


def test_random_search_does_not_collapse_distinct_scalar_types() -> None:
    domain = (ParameterDomain("a", (1, True, 1.0, 1, True)),)
    points = random_search(domain, count=10, seed=9)
    assert len(points) == 3
    assert {(type(point["a"]).__name__, repr(point["a"])) for point in points} == {
        ("int", "1"),
        ("bool", "True"),
        ("float", "1.0"),
    }


def test_random_search_rejects_duplicate_parameter_names() -> None:
    import pytest

    with pytest.raises(ValueError, match="duplicate"):
        random_search(
            (ParameterDomain("a", (1, 2)), ParameterDomain("a", (2, 3))),
            count=1,
            seed=1,
        )


def test_random_search_handles_integer_space_beyond_system_range_limit() -> None:
    # 2**70 does not fit into the length of a normal Python range.
    huge = tuple(ParameterDomain(f"p{i}", (0, 1)) for i in range(70))
    result = random_search(huge, count=3, seed=10)
    assert len(result) == 3
    assert len({tuple(point.items()) for point in result}) == 3


def test_random_search_matches_prior_seeded_sampling_on_unique_small_grid() -> None:
    import random

    expected = random.Random(11).sample(grid_search(domains()), 4)
    assert random_search(domains(), count=4, seed=11) == expected


def test_grid_search_can_take_only_a_small_prefix_without_full_materialization() -> None:
    large = tuple(ParameterDomain(f"p{i}", (0, 1)) for i in range(28))
    points = grid_search(large, limit=3)
    assert len(points) == 3
    assert all(len(point) == 28 for point in points)
    assert points[0] == {f"p{i}": 0 for i in range(28)}


def test_grid_search_rejects_invalid_limit() -> None:
    import pytest

    with pytest.raises(ValueError, match="limit"):
        grid_search(domains(), limit=-2)


def test_bayesian_search_bounded_for_large_parameter_product(monkeypatch) -> None:
    import mutation.parameter as parameter

    def exhaustive_forbidden(_domains, *, limit=None):
        raise AssertionError("Bayesian search must not expand a huge grid")

    monkeypatch.setattr(parameter, "grid_search", exhaustive_forbidden)
    massive = tuple(ParameterDomain(f"k{i}", (0, 1)) for i in range(29))
    result = bayesian_search(massive, [], count=5, seed=14)
    assert len(result) == 5
    assert result == bayesian_search(massive, [], count=5, seed=14)
    assert len({tuple(sorted(point.items())) for point in result}) == 5


def test_bayesian_large_pool_includes_observed_in_domain_points() -> None:
    massive = (ParameterDomain("a", tuple(range(100))), ParameterDomain("b", tuple(range(100))))
    observed = {"a": 99, "b": 99}
    result = bayesian_search(
        massive, [BayesianObservation(observed, score=5000.0)], count=1, seed=7
    )
    assert result == [observed]


def test_bayesian_rejects_duplicate_names_on_large_grid() -> None:
    import pytest

    with pytest.raises(ValueError, match="duplicate"):
        bayesian_search(
            (ParameterDomain("x", tuple(range(100))), ParameterDomain("x", tuple(range(100)))),
            [],
            count=1,
            seed=4,
        )
