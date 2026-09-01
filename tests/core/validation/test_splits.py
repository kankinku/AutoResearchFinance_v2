from __future__ import annotations

from core.validation.cpcv import cpcv_splits
from core.validation.cscv import cscv_splits
from core.validation.gates import hard_gate
from core.validation.walk_forward import walk_forward_splits
from evaluation.metrics import calculate_metrics


def test_walk_forward_splits_have_disjoint_train_and_test_windows() -> None:
    splits = walk_forward_splits(tuple(range(10)), train_size=5, test_size=2, step=2)

    assert splits == (
        (tuple(range(5)), (5, 6)),
        ((2, 3, 4, 5, 6), (7, 8)),
    )
    assert all(not set(train) & set(test) for train, test in splits)


def test_cpcv_and_cscv_produce_all_group_combinations_without_overlap() -> None:
    cpcv = cpcv_splits(tuple(range(6)), groups=3, test_groups=1)
    cscv = cscv_splits(tuple(range(6)), groups=3, test_groups=1)

    assert len(cpcv) == 3
    assert cpcv == cscv
    assert all(not set(train) & set(test) for train, test in cpcv)


def test_hard_gate_returns_explicit_rejection_reasons() -> None:
    metrics = calculate_metrics((100.0, 99.0), (-1.0,), periods_per_year=1)

    result = hard_gate(metrics, min_trade_count=2, min_return=0.0)

    assert result.passed is False
    assert result.reasons == ("trade_count", "total_return")
