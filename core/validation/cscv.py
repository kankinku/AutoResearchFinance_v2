from __future__ import annotations

import itertools
from collections.abc import Sequence


def cscv_splits(
    values: Sequence[int], *, groups: int, test_groups: int
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    if groups <= 1 or not 0 < test_groups < groups:
        raise ValueError("groups must exceed test_groups and both must be positive")
    if len(values) < groups:
        raise ValueError("values must contain at least one item per group")
    partitions = _partition(values, groups)
    splits = []
    for selected in itertools.combinations(range(groups), test_groups):
        selected_set = set(selected)
        test = tuple(
            item
            for index, group in enumerate(partitions)
            if index in selected_set
            for item in group
        )
        train = tuple(
            item
            for index, group in enumerate(partitions)
            if index not in selected_set
            for item in group
        )
        splits.append((train, test))
    return tuple(splits)


def _partition(values: Sequence[int], groups: int) -> tuple[tuple[int, ...], ...]:
    size, remainder = divmod(len(values), groups)
    result: list[tuple[int, ...]] = []
    start = 0
    for index in range(groups):
        width = size + (index < remainder)
        result.append(tuple(values[start : start + width]))
        start += width
    return tuple(result)
