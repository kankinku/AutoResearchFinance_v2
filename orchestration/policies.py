from __future__ import annotations

import random

from memory.frontier import Frontier


def allocate_sources(frontier: Frontier, *, candidate_target: int, seed: int) -> dict[str, int]:
    if candidate_target < 0:
        raise ValueError("candidate_target must be non-negative")
    names = ("exploit", "explore", "crossover", "rescue")
    ratios = (0.40, 0.30, 0.20, 0.10)
    raw = [candidate_target * ratio for ratio in ratios]
    counts = [int(value) for value in raw]
    remainder = candidate_target - sum(counts)
    order = list(range(len(names)))
    random.Random(seed).shuffle(order)
    for index in order[:remainder]:
        counts[index] += 1
    return dict(zip(names, counts, strict=True))
