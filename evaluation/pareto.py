from __future__ import annotations

from collections.abc import Mapping, Sequence


def pareto_frontier(
    objective_vectors: Mapping[str, Sequence[float]], *, maximize: Sequence[bool]
) -> tuple[str, ...]:
    if not objective_vectors or not maximize:
        return ()
    width = len(maximize)
    if any(len(vector) != width for vector in objective_vectors.values()):
        raise ValueError("objective vectors must have equal dimensions")
    keys = tuple(sorted(objective_vectors))
    frontier = tuple(
        key
        for key in keys
        if not any(
            other != key
            and _dominates(objective_vectors[other], objective_vectors[key], maximize)
            for other in keys
        )
    )
    return frontier


def _dominates(left: Sequence[float], right: Sequence[float], maximize: Sequence[bool]) -> bool:
    no_worse = all(
        (a >= b if is_max else a <= b) for a, b, is_max in zip(left, right, maximize, strict=True)
    )
    strictly_better = any(
        (a > b if is_max else a < b) for a, b, is_max in zip(left, right, maximize, strict=True)
    )
    return no_worse and strictly_better
