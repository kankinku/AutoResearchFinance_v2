from __future__ import annotations

from collections.abc import Sequence

from core.validation.cpcv import cpcv_splits


def cscv_splits(
    values: Sequence[int], *, groups: int, test_groups: int
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    return cpcv_splits(values, groups=groups, test_groups=test_groups)
