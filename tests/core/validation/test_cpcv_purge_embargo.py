"""Independent interval-overlap oracle for optional label-aware CPCV splitting."""

import pytest

from core.validation.cpcv import cpcv_splits


def test_label_lookahead_and_embargo_exclude_overlapping_train_samples() -> None:
    samples = tuple(range(9))
    ends = tuple(min(i + 2, 8) for i in samples)
    combinations_found = cpcv_splits(
        samples, groups=3, test_groups=1, label_end_indices=ends, embargo_bars=1
    )
    mid_train, mid_test = combinations_found[1]
    assert mid_test == (3, 4, 5)
    # Test labels cover [3..7]. Train windows [1..3], [2..4],
    # [6..8], [7..8] overlap; index 8 is embargoed.
    assert mid_train == (0,)


def test_embargo_without_label_horizon_only_removes_bars_after_test() -> None:
    train, test = cpcv_splits(
        tuple(range(9)), groups=3, test_groups=1, embargo_bars=1
    )[1]
    assert test == (3, 4, 5)
    assert train == (0, 1, 2, 7, 8)


def test_every_purged_split_matches_independent_interval_oracle() -> None:
    n = 12
    labels = tuple(min(i + (i % 3), n - 1) for i in range(n))
    values = tuple(range(n))
    for train, test in cpcv_splits(
        values, groups=4, test_groups=2, label_end_indices=labels, embargo_bars=2
    ):
        assert not set(train) & set(test)
        assert all(
            all(not (i <= labels[j] and labels[i] >= j) for j in test)
            for i in train
        )
        # Embargo must follow each contiguous union of test label intervals.
        for i in train:
            assert all(
                not (labels[j] < i <= labels[j] + 2)
                for j in test
            )


@pytest.mark.parametrize(
    "ends,embargo",
    [
        ((0, 1), 0),
        ((-1, 2, 2), 0),
        ((1, 0, 2), 0),
        ((0, 1, 3), 0),
        (None, -1),
    ],
)
def test_cpcv_rejects_invalid_label_ends_and_negative_embargo(
    ends: tuple[int, ...] | None, embargo: int
) -> None:
    with pytest.raises(ValueError, match="label|embargo"):
        cpcv_splits(
            tuple(range(3)),
            groups=3,
            test_groups=1,
            label_end_indices=ends,
            embargo_bars=embargo,
        )
