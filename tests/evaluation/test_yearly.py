from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.backtest.engine import Trade
from core.data.contracts import Bar, DataZone, MarketDataSet
from evaluation.yearly import summarize_yearly_performance


def _dataset() -> MarketDataSet:
    bars = tuple(
        Bar(
            datetime(year, month, 2, tzinfo=timezone.utc),
            "QQQ",
            min(100.0, close),
            max(102.0, close),
            min(99.0, close),
            close,
            1_000.0,
        )
        for year, month, close in (
            (2024, 1, 100.0),
            (2024, 12, 110.0),
            (2025, 1, 110.0),
            (2025, 12, 121.0),
        )
    )
    return MarketDataSet("fixture", DataZone.VALIDATION, bars)


def test_yearly_summary_contains_return_and_completed_trade_count() -> None:
    trades = (
        Trade("2024-03-01T00:00:00+00:00", "buy", 100.0, 1.0, 100.0, 0.0, "QQQ"),
        Trade("2024-04-01T00:00:00+00:00", "sell", 101.0, 1.0, 101.0, 0.0, "QQQ"),
        Trade("2025-03-01T00:00:00+00:00", "buy", 110.0, 1.0, 110.0, 0.0, "QQQ"),
        Trade("2025-04-01T00:00:00+00:00", "sell", 111.0, 1.0, 111.0, 0.0, "QQQ"),
    )

    summary = summarize_yearly_performance(_dataset(), (100.0, 110.0, 110.0, 121.0), trades)

    assert [item["year"] for item in summary] == [2024, 2025]
    assert summary[0]["trade_count"] == 1
    assert summary[0]["total_return"] == pytest.approx(0.10)
    assert summary[1]["trade_count"] == 1
    assert summary[1]["total_return"] == pytest.approx(0.10)
    assert summary[0]["complete"] is True


def test_yearly_summary_marks_last_partial_calendar_year() -> None:
    dataset = MarketDataSet(
        "partial",
        DataZone.VALIDATION,
        (
            Bar(datetime(2025, 1, 2, tzinfo=timezone.utc), "QQQ", 100, 101, 99, 100, 1),
            Bar(datetime(2025, 12, 30, tzinfo=timezone.utc), "QQQ", 109, 111, 108, 110, 1),
            Bar(datetime(2026, 1, 2, tzinfo=timezone.utc), "QQQ", 110, 111, 109, 110, 1),
        ),
    )

    summary = summarize_yearly_performance(dataset, (100.0, 110.0, 110.0), ())

    assert summary[0]["complete"] is True
    assert summary[1]["complete"] is False
