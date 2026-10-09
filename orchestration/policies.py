from __future__ import annotations

import random
from collections.abc import Mapping
from math import floor, isfinite
from pathlib import Path

from memory.frontier import Frontier
from research.policy import SearchPolicy, load_policy

SOURCES = ("exploit", "explore", "crossover", "rescue")


def allocate_sources(
    frontier: Frontier,
    *,
    candidate_target: int,
    seed: int,
    policy: SearchPolicy | None = None,
    ratios: Mapping[str, float] | None = None,
) -> dict[str, int]:
    """Deterministically allocate search budgets from canonical policy weights.

    This is planning only. A budget must not be reported as *executed*
    crossover or rescue work before the relevant source has actually run.
    """
    if candidate_target < 0:
        raise ValueError("candidate_target must be non-negative")
    if policy is not None and ratios is not None:
        raise ValueError("specify policy or ratios, not both")
    if ratios is None:
        source_policy = (
            policy or load_policy(Path(__file__).parents[1] / "research/policy.yaml").search
        )
        ratios = {
            "exploit": source_policy.exploit_ratio,
            "explore": source_policy.explore_ratio,
            "crossover": source_policy.crossover_ratio,
            "rescue": source_policy.rescue_ratio,
        }
    if (
        set(ratios) != set(SOURCES)
        or any(not isfinite(value) or value < 0 for value in ratios.values())
        or abs(sum(ratios.values()) - 1) > 1e-9
    ):
        raise ValueError("search ratios must be finite, nonnegative, and sum to 1")
    raw = [candidate_target * ratios[name] for name in SOURCES]
    counts = [floor(value) for value in raw]
    remainder = candidate_target - sum(counts)
    seeded = list(range(len(SOURCES)))
    random.Random(seed).shuffle(seeded)
    order = sorted(seeded, key=lambda index: -(raw[index] - counts[index]))
    for index in order[:remainder]:
        counts[index] += 1
    return dict(zip(SOURCES, counts, strict=True))
