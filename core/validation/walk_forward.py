from __future__ import annotations

from collections.abc import Sequence


def walk_forward_splits(
    values: Sequence[int], *, train_size: int, test_size: int, step: int
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    if min(train_size, test_size, step) <= 0:
        raise ValueError("window sizes and step must be positive")
    result: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    start = 0
    while start + train_size + test_size <= len(values):
        train = tuple(values[start : start + train_size])
        test = tuple(values[start + train_size : start + train_size + test_size])
        result.append((train, test))
        start += step
    return tuple(result)
