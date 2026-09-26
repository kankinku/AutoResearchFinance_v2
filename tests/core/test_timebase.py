from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, MarketDataSet
from core.data.timebase import periods_per_year


def _bars(*, days: int, bars_per_day: int) -> tuple[Bar, ...]:
    values: list[Bar] = []
    for day in range(days):
        start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc) + timedelta(days=day)
        for index in range(bars_per_day):
            timestamp = start + timedelta(minutes=15 * index)
            price = 100.0 + day + index / 100
            values.append(Bar(timestamp, "QQQ", price, price, price, price, 1000))
    return tuple(values)


def test_periods_per_year_uses_timeframe_and_equity_calendar() -> None:
    dataset = MarketDataSet(
        "intraday",
        "development",
        _bars(days=3, bars_per_day=26),
        timeframe="15m",
        calendar="us_equities",
    )

    assert periods_per_year(dataset) == pytest.approx(26 * 252)


def test_periods_per_year_uses_continuous_calendar() -> None:
    dataset = MarketDataSet(
        "crypto",
        "development",
        _bars(days=2, bars_per_day=96),
        timeframe="15m",
        calendar="continuous",
    )

    assert periods_per_year(dataset) == pytest.approx(96 * 365)


def test_daily_and_monthly_annualization_do_not_use_intraday_density() -> None:
    daily = MarketDataSet(
        "daily",
        "development",
        _bars(days=3, bars_per_day=1),
        timeframe="1d",
        calendar="us_equities",
    )
    monthly = MarketDataSet(
        "monthly",
        "development",
        _bars(days=3, bars_per_day=1),
        timeframe="1mo",
        calendar="continuous",
    )

    assert periods_per_year(daily) == pytest.approx(252)
    assert periods_per_year(monthly) == pytest.approx(12)
