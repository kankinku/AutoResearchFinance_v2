"""Shaakuni Liquidity Levels & Order Blocks v1.4, research-only port.

Original © Shaakuni, MPL-2.0: https://mozilla.org/MPL/2.0/
Confirmed-bar order block/mitigation logic is retained. This indicator is NOT
a trading strategy. The Pine timenow/islast panel is explicitly not reproduced
as historical predictive data. No Pine visuals or orders are executed.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Literal, Sequence
from zoneinfo import ZoneInfo

from core.features.pine_liquidity_levels import CompletedLevels, completed_period_levels


@dataclass(frozen=True)
class ShaakuniParams:
    swing_lookback: int = 10
    impulse_atr_multiple: float = 0.7
    zone_lookback: int = 150
    show_order_blocks: bool = True
    show_fresh: bool = True
    show_mitigated: bool = False
    atr_period: int = 14

    def validate(self) -> None:
        if (
            type(self.swing_lookback) is not int
            or not 3 <= self.swing_lookback <= 50
            or type(self.zone_lookback) is not int
            or not 30 <= self.zone_lookback <= 2000
            or type(self.atr_period) is not int
            or self.atr_period != 14
            or type(self.impulse_atr_multiple) not in (int, float)
            or not isfinite(self.impulse_atr_multiple)
            or not 0.1 <= self.impulse_atr_multiple <= 5
            or any(type(x) is not bool for x in (
                self.show_order_blocks, self.show_fresh, self.show_mitigated
            ))
        ):
            raise ValueError("unsupported Shaakuni Pine v1.4 parameters")


@dataclass(frozen=True)
class OrderBlock:
    block_id: int
    side: Literal["BULL", "BEAR"]
    source_bar: int
    confirmed_bar: int
    top: float
    bottom: float
    mitigated_bar: int | None = None


@dataclass(frozen=True)
class ContextBar:
    index: int
    atr: float | None
    levels: CompletedLevels
    day_high_status: Literal["ACTIVE", "SWEEP", "BREAK"]
    day_low_status: Literal["ACTIVE", "SWEEP", "BREAK"]
    created_ids: tuple[int, ...]
    created_bull_ids: tuple[int, ...]
    created_bear_ids: tuple[int, ...]
    mitigated_ids: tuple[int, ...]
    fresh_bull: int
    fresh_bear: int
    retained_count: int


@dataclass(frozen=True)
class ShaakuniResult:
    bars: tuple[ContextBar, ...]
    retained_blocks: tuple[OrderBlock, ...]
    source_license: str = "MPL-2.0"
    source_contract: str = "CONFIRMED_BAR_INDICATOR_ONLY"
    original_live_panel_parity: bool = False
    original_drawings_parity: bool = False
    broker_executable: bool = False
    operational_registry_promoted: bool = False


def session_at(asof: datetime, mode: str = "Auto (DST)") -> str:
    """Historical NY clock study; Pine used timenow (current live clock)."""
    if asof.tzinfo is None or asof.utcoffset() is None:
        raise ValueError("aware timestamp required")
    if mode == "Auto (DST)":
        dt = asof.astimezone(ZoneInfo("America/New_York"))
    elif mode in ("Manual UTC-4 (EDT)", "Manual UTC-5 (EST)"):
        hours = -4 if "UTC-4" in mode else -5
        dt = asof.astimezone(timezone(timedelta(hours=hours)))
    else:
        raise ValueError("unsupported Shaakuni timezone")
    mins = dt.hour * 60 + dt.minute
    if 1200 <= mins < 1440:
        return "Asian"
    if 120 <= mins < 300:
        return "London"
    if 420 <= mins < 600:
        return "New York"
    if 600 <= mins < 720:
        return "London Close"
    return "-"


def compute_shaakuni(
    timestamps: Sequence[datetime],
    opened: Sequence[float],
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    params: ShaakuniParams = ShaakuniParams(),
) -> ShaakuniResult:
    """Use only completed OHLC bars. Original OB selection/mitigation order.

    Current source ATR is used for validating the earlier impulse candle.
    Boxes are retained by confirmation-bar age. Source weekend/timenow shifting
    is excluded because it would change past values using a future wall clock.
    """
    params.validate()
    n = len(timestamps)
    if n > 50_000 or any(len(x) != n for x in (opened, high, low, close)):
        raise ValueError("unaligned or unbounded market data")
    if any(t.tzinfo is None or t.utcoffset() is None for t in timestamps):
        raise ValueError("timezone-aware exchange bars required")
    if any(timestamps[i] <= timestamps[i-1] for i in range(1, n)):
        raise ValueError("nonmonotonic bar dates")
    if any(
        not all(isfinite(v) and v > 0 for v in (o, h, l, c))
        or h < max(o, c) or l > min(o, c)
        for o, h, l, c in zip(opened, high, low, close, strict=True)
    ):
        raise ValueError("invalid OHLC input")

    levels = completed_period_levels(
        [(t, float(h), float(l)) for t, h, l in zip(timestamps, high, low, strict=True)]
    )
    tr: list[float] = []
    atr: float | None = None
    zones: list[OrderBlock] = []
    output: list[ContextBar] = []
    last_bull_bar = last_bear_bar = -1
    next_id = 1
    day_key = None
    day_high = day_low = 0.0

    for i in range(n):
        previous = close[i-1] if i else close[i]
        tr.append(max(high[i]-low[i], abs(high[i]-previous), abs(low[i]-previous)))
        if i == 13:
            atr = sum(tr[:14])/14
        elif i > 13 and atr is not None:
            atr = (atr*13 + tr[-1])/14

        if timestamps[i].date() != day_key:
            day_high, day_low = high[i], low[i]
            day_key = timestamps[i].date()
        else:
            day_high, day_low = max(day_high, high[i]), min(day_low, low[i])
        p = levels[i]
        hs: Literal["ACTIVE", "SWEEP", "BREAK"] = "ACTIVE"
        ls: Literal["ACTIVE", "SWEEP", "BREAK"] = "ACTIVE"
        if p.previous_day_high is not None:
            hs = ("BREAK" if close[i] > p.previous_day_high else
                  "SWEEP" if day_high > p.previous_day_high else "ACTIVE")
        if p.previous_day_low is not None:
            ls = ("BREAK" if close[i] < p.previous_day_low else
                  "SWEEP" if day_low < p.previous_day_low else "ACTIVE")

        created: list[int] = []
        created_bulls: list[int] = []
        created_bears: list[int] = []
        if params.show_order_blocks and atr is not None and i > params.swing_lookback+2:
            for bullish in (True, False):
                # Pine starts at offset=1 and replaces only on strict extremes.
                offsets = range(1, params.swing_lookback+1)
                swing = (
                    max(offsets, key=lambda k: high[i-k]) if bullish else
                    min(offsets, key=lambda k: low[i-k])
                )
                level = high[i-swing] if bullish else low[i-swing]
                if (close[i] <= level if bullish else close[i] >= level) or swing < 3:
                    continue
                middle = (
                    min(range(1, swing), key=lambda k: low[i-k]) if bullish else
                    max(range(1, swing), key=lambda k: high[i-k])
                )
                impulse = -1
                # Original scans offsets middle-1 ... 0 (oldest to newest).
                for k in range(middle-1, -1, -1):
                    candle_body = close[i-k]-opened[i-k]
                    impulse_ok = (
                        candle_body >= atr * params.impulse_atr_multiple
                        if bullish else
                        -candle_body >= atr * params.impulse_atr_multiple
                    )
                    if impulse_ok:
                        impulse = k
                        break
                if impulse < 0:
                    continue
                source_off = middle
                for k in range(impulse+1, middle+1):
                    body = close[i-k]-opened[i-k]
                    if body < 0 if bullish else body > 0:
                        source_off = k
                        break
                source_bar = i-source_off
                fresh = all(
                    (low[i-k] > high[source_bar]) if bullish
                    else (high[i-k] < low[source_bar])
                    for k in range(0, source_off-1)
                ) if source_off >= 2 else True
                if not fresh or source_bar == (last_bull_bar if bullish else last_bear_bar):
                    continue
                if bullish:
                    last_bull_bar = source_bar
                else:
                    last_bear_bar = source_bar
                zones.append(OrderBlock(
                    next_id, "BULL" if bullish else "BEAR",
                    source_bar, i, high[source_bar], low[source_bar],
                ))
                created.append(next_id)
                (created_bulls if bullish else created_bears).append(next_id)
                next_id += 1

        mitigated: list[int] = []
        remaining: list[OrderBlock] = []
        for block in zones:
            if (
                i > block.confirmed_bar and block.mitigated_bar is None
                and high[i] >= block.bottom and low[i] <= block.top
            ):
                block = replace(block, mitigated_bar=i)
                mitigated.append(block.block_id)
            if block.confirmed_bar >= i-params.zone_lookback:
                remaining.append(block)
        zones = remaining
        output.append(ContextBar(
            i, atr, p, hs, ls, tuple(created), tuple(created_bulls),
            tuple(created_bears), tuple(mitigated),
            sum(b.side == "BULL" and b.mitigated_bar is None for b in zones),
            sum(b.side == "BEAR" and b.mitigated_bar is None for b in zones),
            len(zones),
        ))
    return ShaakuniResult(tuple(output), tuple(zones))
