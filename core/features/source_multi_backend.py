"""Additional uniquely defined OHLCV research signals from pinned TA-Lib C and Stock C#.

Original sources cloned under isolated Moon workspace; independent causal Python
math ports with immutable provenance in the Quant feature catalog. The
Alligator lines are deliberately UNshifted: the original future chart plot
offset must never be interpreted as a future-observation trading signal.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import fmean

NumberSeries = Sequence[float | None]
Data = Mapping[str, NumberSeries]

KNOWN = frozenset(
    {
        "talib_adr",
        "talib_rvol",
        "talib_imi",
        "talib_ac",
        "talib_rogers_satchell",
        "stock_elder_bull",
        "stock_elder_bear",
        "stock_starc_upper",
        "stock_starc_lower",
        "stock_alligator_jaw",
        "stock_alligator_teeth",
        "stock_alligator_lips",
    }
)


def _as_float(value: float | None) -> float:
    if value is None:
        raise ValueError("missing source observation")
    return float(value)


def _window(values: NumberSeries, last: int, length: int) -> list[float] | None:
    if last < length - 1:
        return None
    part = values[last - length + 1 : last + 1]
    if any(v is None or not math.isfinite(_as_float(v)) for v in part):
        return None
    return [_as_float(v) for v in part if v is not None]


def _ema(values: NumberSeries, n: int, *, wilder: bool = False) -> list[float | None]:
    alpha = 1 / n if wilder else 2 / (n + 1)
    result: list[float | None] = [None] * len(values)
    level: float | None = None
    for i, v in enumerate(values):
        if v is None:
            level = None
            continue
        if level is None:
            w = _window(values, i, n)
            if w is not None:
                level = fmean(w)
        else:
            level += alpha * (_as_float(v) - level)
        result[i] = level
    return result


def calculate_additional_source(name: str, raw: Data, lookback: int) -> tuple[float | None, ...]:
    if name not in KNOWN:
        raise ValueError("not a registered external formula")
    if not 2 <= lookback <= 252:
        raise ValueError("lookback outside verified range")
    size = len(next(iter(raw.values())))
    if size > 1_000_000 or any(len(values) != size for values in raw.values()):
        raise ValueError("unbounded or misaligned input data")
    out: list[float | None] = [None] * size
    c = raw.get("close", ())
    h = raw.get("high", ())
    low_series = raw.get("low", ())
    o = raw.get("open", ())
    v = raw.get("volume", ())
    if name.startswith("stock_alligator_"):
        median: list[float | None] = [
            (
                (_as_float(h[i]) + _as_float(low_series[i])) / 2
                if h[i] is not None and low_series[i] is not None
                else None
            )
            for i in range(size)
        ]
        return tuple(_ema(median, lookback, wilder=True))
    if name in {"stock_elder_bull", "stock_elder_bear"}:
        ema = _ema(c, lookback)
        for i in range(size):
            spread = h[i] if name.endswith("bull") else low_series[i]
            if ema[i] is not None and spread is not None:
                out[i] = _as_float(spread) - _as_float(ema[i])
        return tuple(out)
    if name.startswith("stock_starc_"):
        natr = 15
        trs: list[float | None] = [None] * size
        for i in range(1, size):
            if any(
                series[j] is None
                for series, j in (
                    (h, i),
                    (low_series, i),
                    (c, i - 1),
                )
            ):
                continue
            high, low, previous = _as_float(h[i]), _as_float(low_series[i]), _as_float(c[i - 1])
            trs[i] = max(high - low, abs(high - previous), abs(low - previous))
        # ATR series starts at bar 15, matching Stock Indicators' Wilder seed.
        atr: list[float | None] = [None] * size
        state: float | None = None
        for i in range(1, size):
            if trs[i] is None:
                state = None
                continue
            if state is None:
                seed = _window(trs, i, natr)
                if seed is not None:
                    state = fmean(seed)
            else:
                state = (state * (natr - 1) + _as_float(trs[i])) / natr
            atr[i] = state
        for i in range(size):
            window = _window(c, i, lookback)
            if window is not None and atr[i] is not None:
                sign = 1 if name.endswith("upper") else -1
                out[i] = fmean(window) + sign * 2.0 * _as_float(atr[i])
        return tuple(out)
    if name == "talib_ac":
        med: list[float | None] = [
            (_as_float(h[i]) + _as_float(low_series[i])) / 2
            if h[i] is not None and low_series[i] is not None
            else None
            for i in range(size)
        ]
        ao: list[float | None] = [None] * size
        for i in range(size):
            wide = _window(med, i, lookback)
            narrow = _window(med, i, 5)
            if wide is not None and narrow is not None:
                ao[i] = fmean(narrow) - fmean(wide)
        for i in range(size):
            signal = _window(ao, i, 5)
            if signal is not None:
                out[i] = signal[-1] - fmean(signal)
        return tuple(out)
    for i in range(size):
        if name == "talib_adr":
            hw, lw = _window(h, i, lookback), _window(low_series, i, lookback)
            if hw is not None and lw is not None:
                out[i] = fmean(a - b for a, b in zip(hw, lw, strict=True))
        elif name == "talib_rvol":
            baseline = _window(v, i - 1, lookback)
            today = v[i]
            if baseline is not None and today is not None:
                avg = fmean(baseline)
                out[i] = _as_float(today) / avg if avg > 0 else 0.0
        elif name == "talib_imi":
            opens = _window(o, i, lookback)
            closes = _window(c, i, lookback)
            if opens is not None and closes is not None:
                gains = sum(
                    max(close - opening, 0) for opening, close in zip(opens, closes, strict=True)
                )
                losses = sum(
                    max(opening - close, 0) for opening, close in zip(opens, closes, strict=True)
                )
                out[i] = 100 * gains / (gains + losses) if gains + losses else 50.0
        elif name == "talib_rogers_satchell":
            op, hi, lo, cl = (_window(seq, i, lookback) for seq in (o, h, low_series, c))
            if op is not None and hi is not None and lo is not None and cl is not None:
                if min((*op, *hi, *lo, *cl)) <= 0:
                    continue
                terms = [
                    math.log(H / C) * math.log(H / opening_value)
                    + math.log(L / C) * math.log(L / opening_value)
                    for opening_value, H, L, C in zip(op, hi, lo, cl, strict=True)
                ]
                mean = fmean(terms)
                out[i] = math.sqrt(252 * mean) if mean > 0 else 0.0
    return tuple(out)
