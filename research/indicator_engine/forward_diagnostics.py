"""Independent cash-exposure diagnostics from canonical research fills.

Market returns on cash days are descriptive, *not* achievable trading PnL.
The output cannot establish alpha, PIT history, or independent OOS evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite, log
from typing import Literal

from core.backtest.engine import Trade
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError


@dataclass(frozen=True)
class ForwardExposureDiagnostic:
    dataset_hash: str
    report_hash: str
    exposed_sessions: int
    cash_only_sessions: int
    entry_count: int
    exit_count: int
    total_execution_cost: float
    flat_market_log_return: float
    exposed_market_log_return: float
    status: Literal["DESCRIPTIVE_DEVELOPMENT_DIAGNOSTIC"] = (
        "DESCRIPTIVE_DEVELOPMENT_DIAGNOSTIC"
    )
    point_in_time_verified: Literal[False] = False
    candidate_promotable: Literal[False] = False


def diagnose_forward_exposure(
    market: MarketDataSet,
    trades: tuple[Trade, ...],
    *,
    start_index: int,
    end_index: int,
) -> ForwardExposureDiagnostic:
    """Replay buys/sells at daily opens and partition close-to-close log moves.

    Session labels are identical to the canonical backtest's bar timestamps.
    Each day's close-to-close move is allocated based on holdings **after**
    that day's open orders, so overnight gaps make the partition directional
    context only, never a cash-vs-invested profit attribution.
    """
    if market.zone != DataZone.DEVELOPMENT:
        raise ResearchCatalogError("only development diagnostics allowed")
    if market.timeframe != "1d" or market.calendar != "us_equities":
        raise ResearchCatalogError("daily US equity bars required")
    if not (0 <= start_index < end_index <= len(market.bars)):
        raise ResearchCatalogError("invalid forward window indices")
    bars = market.bars[start_index:end_index]
    if len({b.symbol for b in bars}) != 1:
        raise ResearchCatalogError("forward diagnostics require one security")
    by_stamp = {bar.timestamp.isoformat(): bar for bar in bars}
    if len(by_stamp) != len(bars):
        raise ResearchCatalogError("duplicate forward market timestamps")
    grouped: dict[str, list[Trade]] = {}
    cost = 0.0
    entries = exits = 0
    for trade in trades:
        bar = by_stamp.get(trade.timestamp)
        if bar is None:
            raise ResearchCatalogError("trade timestamp outside forward window")
        if (
            trade.symbol != bar.symbol
            or trade.side not in {"buy", "sell"}
            or not all(isfinite(x) for x in (
                trade.price, trade.quantity, trade.notional, trade.cost,
            ))
            or trade.quantity <= 0 or trade.cost < 0
            or not isclose(trade.price, bar.open, rel_tol=1e-10, abs_tol=1e-8)
            or not isclose(trade.notional, trade.price * trade.quantity,
                           rel_tol=1e-9, abs_tol=1e-8)
        ):
            raise ResearchCatalogError("invalid trade price or quantity integrity")
        grouped.setdefault(trade.timestamp, []).append(trade)
        cost += trade.cost
        if trade.side == "buy":
            entries += 1
        else:
            exits += 1
    holdings = 0.0
    exposed = flat = 0
    exposed_log = flat_log = 0.0
    prev_close: float | None = None
    for bar in bars:
        for trade in grouped.get(bar.timestamp.isoformat(), ()):
            if trade.side == "buy":
                holdings += trade.quantity
            else:
                if trade.quantity > holdings + 1e-8:
                    raise ResearchCatalogError("sell exceeds held shares")
                holdings -= trade.quantity
                if abs(holdings) < 1e-8:
                    holdings = 0.0
        active = holdings > 1e-8
        if active:
            exposed += 1
        else:
            flat += 1
        if prev_close is not None:
            daily = log(bar.close / prev_close)
            if active:
                exposed_log += daily
            else:
                flat_log += daily
        prev_close = bar.close
    digest = content_hash({
        "version": "forward-exposure-diagnostic-v1",
        "market": market.dataset_hash,
        "start": start_index, "end": end_index,
        "fills": [(t.timestamp, t.side, t.price, t.quantity, t.cost) for t in trades],
        "exposed_sessions": exposed, "cash_only_sessions": flat,
        "flat_market_log_return": flat_log, "exposed_market_log_return": exposed_log,
        "total_execution_cost": cost,
    })
    return ForwardExposureDiagnostic(
        dataset_hash=market.dataset_hash, report_hash=digest,
        exposed_sessions=exposed, cash_only_sessions=flat,
        entry_count=entries, exit_count=exits, total_execution_cost=cost,
        flat_market_log_return=flat_log, exposed_market_log_return=exposed_log,
    )
