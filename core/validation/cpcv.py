from __future__ import annotations

import itertools
from collections.abc import Sequence


def cpcv_splits(
    values: Sequence[int],
    *,
    groups: int,
    test_groups: int,
    label_end_indices: Sequence[int] | None = None,
    embargo_bars: int = 0,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    if groups <= 1 or not 0 < test_groups < groups:
        raise ValueError("groups must exceed test_groups and both must be positive")
    if not isinstance(embargo_bars, int) or isinstance(embargo_bars, bool) or embargo_bars < 0:
        raise ValueError("embargo_bars must be nonnegative")
    if label_end_indices is not None:
        if len(label_end_indices) != len(values) or any(
            isinstance(end, bool)
            or not isinstance(end, int)
            or end < index
            or end >= len(values)
            for index, end in enumerate(label_end_indices)
        ):
            raise ValueError("label_end_indices must be ordered valid inclusive end positions")
    partitions = _partition(tuple(range(len(values))), groups)
    result = []
    for selected in itertools.combinations(range(groups), test_groups):
        selected_set = set(selected)
        test_positions = tuple(
            pos
            for index, group in enumerate(partitions)
            if index in selected_set
            for pos in group
        )
        train_positions = tuple(
            pos
            for index, group in enumerate(partitions)
            if index not in selected_set
            for pos in group
        )
        if label_end_indices is not None or embargo_bars:
            ends = (
                label_end_indices
                if label_end_indices is not None
                else tuple(range(len(values)))
            )
            # Merge test label-availability intervals, then remove training
            # labels overlapping those intervals and embargo following each.
            intervals: list[tuple[int, int]] = []
            for test_pos in test_positions:
                right = ends[test_pos]
                if intervals and test_pos <= intervals[-1][1] + 1:
                    left, previous_end = intervals[-1]
                    intervals[-1] = (left, max(right, previous_end))
                else:
                    intervals.append((test_pos, right))
            train_positions = tuple(
                pos
                for pos in train_positions
                if all(
                    not (pos <= right and ends[pos] >= left)
                    and not (right < pos <= right + embargo_bars)
                    for left, right in intervals
                )
            )
        result.append(
            (
                tuple(values[pos] for pos in train_positions),
                tuple(values[pos] for pos in test_positions),
            )
        )
    return tuple(result)


def _partition(values: Sequence[int], groups: int) -> tuple[tuple[int, ...], ...]:
    if len(values) < groups:
        raise ValueError("values must contain at least one item per group")
    size, remainder = divmod(len(values), groups)
    result: list[tuple[int, ...]] = []
    start = 0
    for index in range(groups):
        width = size + (index < remainder)
        result.append(tuple(values[start : start + width]))
        start += width
    return tuple(result)
