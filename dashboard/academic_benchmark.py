"""Same-vintage QQQ price-only passive hurdle for the academic read-only monitor.

Uses the *exact* dataset hash used by the monitored AlgorithmPlan session.
No dividends, reinvestment, splits reconstruction, PIT or independent OOS claims.
"""

from __future__ import annotations

from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Any

from core.data.contracts import DataZone, MarketDataSet
from core.data.parquet import ParquetDataProvider
from research.indicator_engine.strategy_adapter import _COST

_QQQ_RELATIVE = Path("data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet")
_INITIAL_CASH = 10_000.0


def inferred_qqq_market_path(checkpoint_dir: Path) -> Path | None:
    """Infer only the registered server layout, never follow caller URL paths."""
    d = checkpoint_dir.resolve()
    if (
        d.name != "academic-gpt-checkpoints"
        or d.parent.name != "research"
        or d.parent.parent.name != "moon-http"
        or d.parent.parent.parent.name != "state"
    ):
        return None
    return d.parents[3] / _QQQ_RELATIVE


def qqq_buyhold_for_session(
    path: Path | None,
    *,
    expected_dataset_hash: str,
) -> dict[str, Any]:
    """Returns comparable development price-only metrics or explicit UNAVAILABLE."""
    if path is None or not path.is_file() or path.is_symlink():
        return {"status": "UNAVAILABLE", "reason": "QQQ_RAW_REFERENCE_NOT_FOUND"}
    try:
        stats = path.stat()
        return _cached_qqq_buyhold(
            str(path.resolve()),
            expected_dataset_hash,
            stats.st_mtime_ns,
            stats.st_size,
        )
    except (OSError, ValueError, TypeError):
        return {"status": "UNAVAILABLE", "reason": "QQQ_REFERENCE_READ_FAILED"}


@lru_cache(maxsize=12)
def _cached_qqq_buyhold(
    file_path: str,
    expected_dataset_hash: str,
    mtime_ns: int,
    file_size: int,
) -> dict[str, Any]:
    del mtime_ns, file_size  # memoize only when file metadata is unchanged
    market = ParquetDataProvider.read(Path(file_path))
    return calculate_qqq_buyhold(market, expected_dataset_hash=expected_dataset_hash)


def calculate_qqq_buyhold(
    market: MarketDataSet,
    *,
    expected_dataset_hash: str,
    initial_cash: float = _INITIAL_CASH,
) -> dict[str, Any]:
    """Buy at first sample OPEN, hold through last CLOSE with 8bp buy costs.

    Holdings are fractional. The last CLOSE is mark-to-market, with no
    hypothetical sale, dividend income, taxes or reinvestment.
    """
    if market.dataset_hash != expected_dataset_hash:
        return {"status": "UNAVAILABLE", "reason": "QQQ_DATASET_HASH_MISMATCH"}
    if (
        market.zone != DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or len(market.bars) < 2
        or {b.symbol for b in market.bars} != {"QQQ"}
        or any(
            a.timestamp >= b.timestamp for a, b in zip(market.bars, market.bars[1:], strict=False)
        )
        or not isfinite(initial_cash)
        or initial_cash <= 0
        or market.provenance is None
        or market.provenance.corporate_action_policy != "raw"
    ):
        return {"status": "UNAVAILABLE", "reason": "QQQ_REFERENCE_INCOMPATIBLE"}
    first, last = market.bars[0], market.bars[-1]
    # Exact cost version of the academic evaluator (1bp commission,
    # 2bp spread, 5bp slippage = 8bp buy). Never mark a sell cost unless
    # the portfolio is liquidated; end-of-window is a valuation, not sale.
    buy_cost_rate = _COST.calculate(1.0, side="buy", stress_multiplier=1.0).total
    invested_notional = initial_cash / (1.0 + buy_cost_rate)
    cost = _COST.calculate(invested_notional, side="buy", stress_multiplier=1.0).total
    remaining_cash = initial_cash - invested_notional - cost
    shares = invested_notional / first.open
    final_equity = remaining_cash + shares * last.close
    price_only_gross = last.close / first.open - 1.0
    buy_cost_return = final_equity / initial_cash - 1.0
    high_watermark, max_drawdown = initial_cash, 0.0
    for bar in market.bars:
        equity = remaining_cash + shares * bar.close
        high_watermark = max(high_watermark, equity)
        max_drawdown = max(max_drawdown, 1.0 - equity / high_watermark)
    duration_years = (last.timestamp - first.timestamp).total_seconds() / (365.25 * 86400)
    if duration_years <= 0:
        return {"status": "UNAVAILABLE", "reason": "QQQ_INVALID_WINDOW"}
    return {
        "status": "DEVELOPMENT_ONLY",
        "symbol": "QQQ",
        "dataset_hash": market.dataset_hash,
        "first_date": first.timestamp.date().isoformat(),
        "last_date": last.timestamp.date().isoformat(),
        "trading_bars": len(market.bars),
        "first_open": first.open,
        "last_close": last.close,
        "initial_cash": initial_cash,
        "final_equity": final_equity,
        "price_only_gross_total_return": price_only_gross,
        "total_return": buy_cost_return,
        "cagr": (final_equity / initial_cash) ** (1 / duration_years) - 1,
        "max_drawdown": max_drawdown,
        "buy_cost_bps": buy_cost_rate * 10_000,
        "buy_cost_amount": cost,
        "no_end_liquidation": True,
        "dividends_included": False,
        "dividends_reinvested": False,
        "point_in_time_verified": False,
        "independent_oos_approved": False,
        "independent_benchmark_verified": False,
        "method": "first_open_buy_last_close_mark_price_only_single_buy_cost",
    }
