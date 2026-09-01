from __future__ import annotations

from datetime import datetime, timezone

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, MarketDataSet


def test_fixture_backtest_produces_isolated_result_contract() -> None:
    dataset = MarketDataSet(
        "data-v1",
        "development",
        (
            Bar(datetime(2024, 1, 1, tzinfo=timezone.utc), "TEST", 100, 101, 99, 100, 1000),
            Bar(datetime(2024, 1, 2, tzinfo=timezone.utc), "TEST", 100, 103, 100, 103, 1000),
            Bar(datetime(2024, 1, 3, tzinfo=timezone.utc), "TEST", 103, 104, 99, 101, 1000),
        ),
    )
    request = BacktestRequest("run-1", "strategy-hash", dataset, initial_cash=10_000)

    result = BacktestEngine().run(request)

    assert result.run_id == "run-1"
    assert result.strategy_hash == "strategy-hash"
    assert result.data_hash == dataset.dataset_hash
    assert result.equity_curve_hash
    assert result.exit_status == "SUCCEEDED"
