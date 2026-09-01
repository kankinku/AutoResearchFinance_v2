from __future__ import annotations

import pytest

from evaluation.benchmark import compare_benchmarks


def test_compare_benchmarks_calculates_total_and_excess_returns() -> None:
    comparison = compare_benchmarks(
        (100.0, 110.0, 121.0),
        (100.0, 105.0, 110.0),
        (100.0, 108.0, 115.0),
        qqq_distributions=(0.0, 0.0, 1.0),
        periods_per_year=2,
    )

    assert comparison.strategy_total_return == pytest.approx(0.21)
    assert comparison.qqq_total_return == pytest.approx(0.11)
    assert comparison.nasdaq_total_return == pytest.approx(0.15)
    assert comparison.qqq_excess_return == pytest.approx(0.10)
    assert comparison.nasdaq_excess_return == pytest.approx(0.06)
    assert comparison.qqq_outperformed is True


def test_compare_benchmarks_requires_same_length_positive_curves() -> None:
    with pytest.raises(ValueError, match="same length"):
        compare_benchmarks((100.0, 110.0), (100.0,), (100.0, 105.0))
