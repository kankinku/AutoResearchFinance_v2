from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from core.backtest.engine import Trade
from core.data.contracts import MarketDataSet


def summarize_yearly_performance(
    dataset: MarketDataSet,
    equity_curve: Sequence[float],
    trades: Sequence[Trade],
) -> tuple[dict[str, Any], ...]:
    """Return calendar-year returns and completed round-trip trade counts.

    A completed trade is represented by a sell execution.  The equity curve is
    aligned to dataset bars for single-symbol runs and to sorted unique bar
    timestamps for the multi-symbol engine output.
    """

    if not dataset.bars or not equity_curve:
        return ()
    timestamps = _curve_timestamps(dataset, len(equity_curve))
    if len(timestamps) != len(equity_curve):
        return ()
    years: dict[int, list[int]] = {}
    for index, timestamp in enumerate(timestamps):
        years.setdefault(timestamp.year, []).append(index)
    trade_counts = Counter(
        datetime.fromisoformat(trade.timestamp).year
        for trade in trades
        if trade.side.lower() == "sell"
    )
    first_timestamp = timestamps[0]
    last_timestamp = timestamps[-1]
    records: list[dict[str, Any]] = []
    for year, indices in sorted(years.items()):
        start = float(equity_curve[indices[0]])
        end = float(equity_curve[indices[-1]])
        total_return = end / start - 1.0 if start > 0 else 0.0
        peak = start
        max_drawdown = 0.0
        for index in indices:
            value = float(equity_curve[index])
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = max(max_drawdown, 1.0 - value / peak)
        complete = _is_complete_year(year, first_timestamp, last_timestamp)
        records.append(
            {
                "year": year,
                "period_start": timestamps[indices[0]].isoformat(),
                "period_end": timestamps[indices[-1]].isoformat(),
                "complete": complete,
                "trade_count": int(trade_counts.get(year, 0)),
                "total_return": total_return,
                "max_drawdown": max_drawdown,
            }
        )
    return tuple(records)


def _curve_timestamps(dataset: MarketDataSet, width: int) -> tuple[datetime, ...]:
    bar_timestamps = tuple(bar.timestamp for bar in dataset.bars)
    if len(bar_timestamps) == width:
        return bar_timestamps
    return tuple(sorted(set(bar_timestamps)))


def _is_complete_year(year: int, first: datetime, last: datetime) -> bool:
    if year == first.year and first.month != 1:
        return False
    if year == last.year and last.month != 12:
        return False
    return True
