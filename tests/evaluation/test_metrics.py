from __future__ import annotations

import pytest

from evaluation.metrics import calculate_metrics


def test_metrics_calculate_return_drawdown_trade_and_risk_values() -> None:
    metrics = calculate_metrics(
        (100.0, 110.0, 105.0, 120.0),
        (10.0, -5.0, 15.0),
        periods_per_year=3,
    )

    assert metrics.total_return == pytest.approx(0.2)
    assert metrics.cagr == pytest.approx(0.2)
    assert metrics.max_drawdown == pytest.approx(5 / 110)
    assert metrics.win_rate == pytest.approx(2 / 3)
    assert metrics.profit_factor == pytest.approx(5.0)
    assert metrics.trade_count == 3


def test_metrics_mark_insufficient_evidence_without_nan() -> None:
    metrics = calculate_metrics((100.0,), (), periods_per_year=252)

    assert metrics.total_return == 0.0
    assert metrics.sharpe is None
    assert metrics.sortino is None
    assert metrics.profit_factor is None
