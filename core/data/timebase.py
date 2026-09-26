from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from statistics import median

from core.data.contracts import MarketDataSet

_INTRADAY_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
}


def periods_per_year(dataset: MarketDataSet) -> float:
    """Return the annualization factor implied by dataset timeframe/calendar metadata."""

    if dataset.timeframe == "1mo":
        return 12.0
    if dataset.timeframe == "1w":
        return 52.0

    sessions = 365.0 if dataset.calendar == "continuous" else 252.0
    if dataset.timeframe == "1d":
        return sessions

    minutes = _INTRADAY_MINUTES.get(dataset.timeframe)
    if minutes is None:
        raise ValueError(f"unsupported dataset timeframe: {dataset.timeframe}")
    if dataset.calendar == "continuous":
        return sessions * (1440.0 / minutes)

    observed = _observed_bars_per_session(dataset)
    if observed > 1:
        return sessions * observed
    return sessions * (390.0 / minutes)


def equity_timestamps(dataset: MarketDataSet, width: int) -> tuple[datetime, ...]:
    """Align an engine equity curve to dataset timestamps for one or many symbols."""

    timestamps = tuple(bar.timestamp for bar in dataset.bars)
    if len(timestamps) == width:
        return timestamps
    unique = tuple(sorted(set(timestamps)))
    if len(unique) != width:
        raise ValueError("equity curve cannot be aligned to dataset timestamps")
    return unique


def equity_returns(equity_curve: Sequence[float]) -> tuple[float, ...]:
    if any(value <= 0 for value in equity_curve):
        raise ValueError("equity curve must contain positive values")
    return tuple(
        current / previous - 1.0
        for previous, current in zip(equity_curve, equity_curve[1:], strict=False)
    )


def _observed_bars_per_session(dataset: MarketDataSet) -> float:
    timestamps = sorted({bar.timestamp for bar in dataset.bars})
    if not timestamps:
        return 1.0
    counts = Counter(timestamp.date() for timestamp in timestamps)
    return float(median(counts.values()))
