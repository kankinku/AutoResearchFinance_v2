from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from typing import TypeAlias

ParameterValue: TypeAlias = int | float | str | bool


@dataclass(frozen=True)
class ParameterDomain:
    name: str
    values: tuple[ParameterValue, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("parameter name cannot be empty")
        if not self.values:
            raise ValueError(f"parameter domain cannot be empty: {self.name}")


@dataclass(frozen=True)
class BayesianObservation:
    parameters: dict[str, ParameterValue]
    score: float


ParameterPoint: TypeAlias = dict[str, ParameterValue]


def grid_search(domains: tuple[ParameterDomain, ...]) -> list[ParameterPoint]:
    names = [domain.name for domain in domains]
    return [
        dict(zip(names, values, strict=True))
        for values in itertools.product(*(d.values for d in domains))
    ]


def random_search(
    domains: tuple[ParameterDomain, ...], *, count: int, seed: int
) -> list[ParameterPoint]:
    if count < 0:
        raise ValueError("count must be non-negative")
    points = grid_search(domains)
    generator = random.Random(seed)
    if count <= len(points):
        indices = generator.sample(range(len(points)), count)
        return [points[index] for index in indices]
    return [points[generator.randrange(len(points))] for _ in range(count)]


def bayesian_search(
    domains: tuple[ParameterDomain, ...],
    observations: list[BayesianObservation],
    *,
    count: int,
    seed: int,
) -> list[ParameterPoint]:
    if count < 0:
        raise ValueError("count must be non-negative")
    candidates = grid_search(domains)
    if not candidates or count == 0:
        return []
    generator = random.Random(seed)
    selected: list[ParameterPoint] = []
    remaining = candidates.copy()
    for _ in range(min(count, len(candidates))):
        scored = [
            (
                _acquisition(point, observations, selected),
                generator.random(),
                point,
            )
            for point in remaining
        ]
        _, _, winner = max(scored, key=lambda item: (item[0], item[1], _stable_point(item[2])))
        selected.append(winner)
        remaining.remove(winner)
    return selected


def _acquisition(
    point: ParameterPoint,
    observations: list[BayesianObservation],
    selected: list[ParameterPoint],
) -> float:
    exact_scores = [obs.score for obs in observations if obs.parameters == point]
    if exact_scores:
        mean = sum(exact_scores) / len(exact_scores)
        uncertainty = 0.0
    elif observations:
        weights = [math.exp(-_distance(point, obs.parameters)) for obs in observations]
        total_weight = sum(weights)
        mean = (
            sum(weight * obs.score for weight, obs in zip(weights, observations, strict=True))
            / total_weight
        )
        uncertainty = 1.0 / math.sqrt(total_weight)
    else:
        mean, uncertainty = 0.0, 1.0
    diversity_penalty = 0.05 * sum(_distance(point, other) == 0 for other in selected)
    return mean + 0.1 * uncertainty - diversity_penalty


def _distance(left: ParameterPoint, right: ParameterPoint) -> float:
    keys = set(left) | set(right)
    return float(sum(left.get(key) != right.get(key) for key in keys))


def _stable_point(point: ParameterPoint) -> str:
    return repr(sorted(point.items()))
