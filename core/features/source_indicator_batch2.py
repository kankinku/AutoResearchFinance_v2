"""Quant V3 Batch 2: OHLCV causal technical indicators and explicit candle geometry.

Mathematical reference: pandas-ta-classic MIT, pinned
7c669b033582d53b70aa68b6388796d19ce33979.
This is independent, documented scalar output, not a direct source copy.
Candle thresholds are deliberately simplified and NOT TA-Lib parity.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import fmean

Numbers = Sequence[float | None]
Series = Mapping[str, Numbers]

BATCH2_NUMERIC: frozenset[str] = frozenset(
    {
        "bias_ratio",
        "chande_forecast_oscillator",
        "absolute_price_oscillator",
        "percentage_price_oscillator",
        "psychological_line",
        "kdj_j",
        "brar_ar",
        "brar_br",
        "ttm_trend",
        "acceleration_band_upper",
        "market_facilitation_index",
        "williams_ad",
        "price_volume_rank",
        "thermometer",
        "pretty_good_oscillator",
    }
)
BATCH2_CANDLES: frozenset[str] = frozenset(
    {
        "hanging_man",
        "inverted_hammer",
        "belt_hold",
        "harami_cross",
        "matching_low",
        "high_wave",
        "long_legged_doji",
        "three_inside",
    }
)
BATCH2_PORTS = BATCH2_NUMERIC | BATCH2_CANDLES


def _valid(values: Numbers, at: int) -> float | None:
    if at < 0 or at >= len(values):
        return None
    value = values[at]
    if value is None or not math.isfinite(float(value)):
        return None
    return float(value)


def _as_float(value: float | None) -> float:
    if value is None:
        raise ValueError("non-finite or missing numeric value")
    return float(value)


def _window(values: Numbers, index: int, count: int) -> list[float] | None:
    if count <= 0 or index < count - 1:
        return None
    vals = [_valid(values, j) for j in range(index - count + 1, index + 1)]
    return None if any(v is None for v in vals) else [float(v) for v in vals if v is not None]


def _sma(values: Numbers, period: int) -> list[float | None]:
    return [
        fmean(window) if (window := _window(values, i, period)) is not None else None
        for i in range(len(values))
    ]


def _ema(values: Numbers, period: int, *, alpha: float | None = None) -> list[float | None]:
    """SMA warmup, causal recursive EMA or Wilder/RMA smoothing."""
    if period < 1:
        raise ValueError("period must be positive")
    alpha = 2 / (period + 1) if alpha is None else alpha
    result: list[float | None] = [None] * len(values)
    state: float | None = None
    for i in range(len(values)):
        v = _valid(values, i)
        if v is None:
            state = None
            continue
        if state is None:
            window = _window(values, i, period)
            if window is not None:
                state = fmean(window)
        else:
            state += alpha * (v - state)
        result[i] = state
    return result


def _true_range(high: Numbers, low: Numbers, close: Numbers) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(close)):
        hi, lo, previous = _valid(high, i), _valid(low, i), _valid(close, i - 1)
        if hi is None or lo is None or hi < lo or (i > 0 and previous is None):
            out.append(None)
        elif i == 0:
            out.append(hi - lo)
        else:
            assert previous is not None
            out.append(max(hi - lo, abs(hi - previous), abs(lo - previous)))
    return out


def _regression_forecast(values: list[float]) -> float:
    count = len(values)
    if count < 2:
        return values[-1]
    mean = fmean(values)
    midpoint = (count - 1) / 2
    slope = sum((j - midpoint) * (v - mean) for j, v in enumerate(values))
    slope /= sum((j - midpoint) ** 2 for j in range(count))
    return mean + slope * midpoint


def _geometry(name: str, series: Series, output: list[float | None]) -> None:
    op, hi, lo, cl = (series[key] for key in ("open", "high", "low", "close"))
    for i in range(len(cl)):
        bars = (
            3
            if name == "three_inside"
            else 2
            if name in {"harami_cross", "matching_low", "hanging_man", "inverted_hammer"}
            else 1
        )
        if i < bars - 1:
            continue
        needed = list(range(i - bars + 1, i + 1))
        row = [(_valid(op, j), _valid(hi, j), _valid(lo, j), _valid(cl, j)) for j in needed]
        if any(any(v is None for v in item) for item in row):
            continue
        frame = [
            (_as_float(a), _as_float(b), _as_float(c), _as_float(d))
            for a, b, c, d in row
            if None not in (a, b, c, d)
        ]
        if any(
            h < max(o, c) or low_value > min(o, c) or low_value > h for o, h, low_value, c in frame
        ):
            continue
        opening, high, low, close = frame[-1]
        rng = high - low
        body = abs(opening - close)
        upper = high - max(opening, close)
        lower = min(opening, close) - low
        sign = 1 if close > opening else -1 if close < opening else 0
        value = 0.0
        if rng > 0:
            if name == "hanging_man":
                previous = frame[-2]
                value = -float(
                    body <= 0.35 * rng
                    and lower >= 0.55 * rng
                    and upper <= 0.12 * rng
                    and min(opening, close) >= previous[1] - 0.15 * (previous[1] - previous[2])
                )
            elif name == "inverted_hammer":
                previous = frame[-2]
                value = float(
                    body <= 0.35 * rng
                    and upper >= 0.55 * rng
                    and lower <= 0.12 * rng
                    and max(opening, close) <= max(previous[0], previous[3])
                )
            elif name == "belt_hold":
                value = float(sign) * float(
                    body >= 0.70 * rng
                    and ((sign > 0 and lower <= 0.05 * rng) or (sign < 0 and upper <= 0.05 * rng))
                )
            elif name == "high_wave":
                value = float(sign) * float(
                    body <= 0.25 * rng and lower >= 0.30 * rng and upper >= 0.30 * rng
                )
            elif name == "long_legged_doji":
                value = float(body <= 0.10 * rng and lower >= 0.40 * rng and upper >= 0.40 * rng)
            elif name == "harami_cross":
                previous = frame[-2]
                prev_o, prev_h, prev_l, prev_c = previous
                prior_body = abs(prev_c - prev_o)
                value = float(1 if prev_c < prev_o else -1) * float(
                    prior_body >= 0.50 * (prev_h - prev_l)
                    and body <= 0.10 * rng
                    and min(opening, close) >= min(prev_o, prev_c)
                    and max(opening, close) <= max(prev_o, prev_c)
                )
            elif name == "matching_low":
                previous = frame[-2]
                prev_o, prev_h, prev_l, prev_c = previous
                value = float(
                    close < opening
                    and prev_c < prev_o
                    and abs(close - prev_c) <= 0.05 * (prev_h - prev_l)
                )
            elif name == "three_inside":
                first, middle, _ = frame
                f_o, f_h, f_l, f_c = first
                m_o, _, _, m_c = middle
                direction = 1 if f_c < f_o else -1 if f_c > f_o else 0
                value = float(direction) * float(
                    abs(f_c - f_o) > 0.45 * (f_h - f_l)
                    and abs(m_c - m_o) <= 0.50 * abs(f_c - f_o)
                    and min(m_o, m_c) >= min(f_o, f_c)
                    and max(m_o, m_c) <= max(f_o, f_c)
                    and (close - opening) * direction > 0
                    and (close - f_o) * direction > 0
                )
        output[i] = value


def calculate_batch2(
    name: str,
    series: Series,
    period: int,
    parameters: Mapping[str, int | float | str | bool],
) -> tuple[float | None, ...]:
    """Compute a full aligned series; do not access bars after index i."""
    if name not in BATCH2_PORTS:
        raise ValueError("unsupported external source indicator")
    if not 1 <= period <= 252:
        raise ValueError("invalid lookback")
    size = len(next(iter(series.values())))
    output: list[float | None] = [None] * size
    if name in BATCH2_CANDLES:
        _geometry(name, series, output)
        return tuple(output)

    close = series.get("close", ())
    high = series.get("high", ())
    low = series.get("low", ())
    opened = series.get("open", ())
    volume = series.get("volume", ())
    close_sma = _sma(close, period) if close else []
    fast = int(parameters.get("fast", 12))
    if name in {"absolute_price_oscillator", "percentage_price_oscillator"}:
        if not 1 <= fast < period:
            raise ValueError("invalid oscillator fast period")
        fast_ma = _sma(close, fast)
    else:
        fast_ma = []

    if name == "kdj_j":
        signal = int(parameters.get("signal", 3))
        if not 1 <= signal <= period:
            raise ValueError("invalid KDJ signal smoothing")
        fast_k: list[float | None] = [None] * size
        for i in range(size):
            hw, lw, c = _window(high, i, period), _window(low, i, period), _valid(close, i)
            if hw is not None and lw is not None and c is not None:
                denom = max(hw) - min(lw)
                fast_k[i] = 100 * (c - min(lw)) / denom if denom else 0.0
        k = _ema(fast_k, signal, alpha=1 / signal)
        d = _ema(k, signal, alpha=1 / signal)
    else:
        k, d = [], []

    if name == "pretty_good_oscillator":
        atr = _ema(_true_range(high, low, close), period, alpha=1 / period)
        smooth_atr = _ema(atr, period)
    else:
        smooth_atr = []

    for i in range(size):
        c = _valid(close, i)
        if name == "bias_ratio":
            mean = close_sma[i]
            if c is not None and mean not in (None, 0):
                output[i] = c / float(mean) - 1
        elif name == "chande_forecast_oscillator":
            window = _window(close, i, period)
            if window is not None and c not in (None, 0):
                output[i] = 100 * (c - _regression_forecast(window)) / c
        elif name in {"absolute_price_oscillator", "percentage_price_oscillator"}:
            slow = close_sma[i]
            rapid = fast_ma[i]
            if slow is not None and rapid is not None:
                if name == "absolute_price_oscillator":
                    output[i] = rapid - slow
                elif slow != 0:
                    output[i] = 100 * (rapid - slow) / slow
        elif name == "psychological_line":
            if i >= period:
                closes = _window(close, i, period + 1)
                if closes is not None:
                    output[i] = (
                        100 * sum(b > a for a, b in zip(closes, closes[1:], strict=False)) / period
                    )
        elif name == "kdj_j":
            if k[i] is not None and d[i] is not None:
                output[i] = 3 * _as_float(k[i]) - 2 * _as_float(d[i])
        elif name == "ttm_trend":
            if i >= period:
                highs = _window(high, i - 1, period)
                lows = _window(low, i - 1, period)
                if highs is not None and lows is not None and c is not None:
                    benchmark = fmean(
                        (h + low_value) / 2 for h, low_value in zip(highs, lows, strict=True)
                    )
                    output[i] = 1.0 if c > benchmark else -1.0
        elif name == "acceleration_band_upper":
            highs, lows = _window(high, i, period), _window(low, i, period)
            if highs is not None and lows is not None:
                values = []
                for h, low_value in zip(highs, lows, strict=True):
                    denom = h + low_value
                    if denom == 0:
                        break
                    values.append(h * (1 + (h - low_value) / denom))
                if len(values) == period:
                    output[i] = fmean(values)
        elif name == "market_facilitation_index":
            hi, lo, v = _valid(high, i), _valid(low, i), _valid(volume, i)
            if hi is not None and lo is not None and v is not None and hi >= lo:
                output[i] = (hi - lo) / v if v > 0 else 0.0 if hi == lo else None
        elif name == "price_volume_rank":
            last, prior = _valid(volume, i), _valid(volume, i - 1)
            prev_close = _valid(close, i - 1)
            if i > 0 and None not in (c, last, prior, prev_close):
                assert c is not None and last is not None
                assert prior is not None and prev_close is not None
                output[i] = float(
                    (1 if last >= prior else 2) if c >= prev_close else (3 if last >= prior else 4)
                )
        elif name == "thermometer":
            hi, lo = _valid(high, i), _valid(low, i)
            prev_hi, prev_lo = _valid(high, i - 1), _valid(low, i - 1)
            if i > 0 and None not in (hi, lo, prev_hi, prev_lo):
                assert hi is not None and lo is not None
                assert prev_hi is not None and prev_lo is not None
                output[i] = max(abs(hi - prev_hi), abs(lo - prev_lo))
        elif name == "williams_ad":
            hi, lo = _valid(high, i), _valid(low, i)
            prev_c = _valid(close, i - 1)
            if i > 0 and hi is not None and lo is not None and c is not None and prev_c is not None:
                previous = output[i - 1] if i > 1 else 0.0
                if previous is None:
                    continue
                increment = (
                    c - min(lo, prev_c)
                    if c > prev_c
                    else c - max(hi, prev_c)
                    if c < prev_c
                    else 0.0
                )
                output[i] = previous + increment
        elif name in {"brar_ar", "brar_br"}:
            if name == "brar_ar":
                highs = _window(high, i, period)
                lows = _window(low, i, period)
                opens = _window(opened, i, period)
                if None not in (highs, lows, opens):
                    assert highs is not None and lows is not None and opens is not None
                    up = sum(max(0.0, h - o) for h, o in zip(highs, opens, strict=True))
                    down = sum(
                        max(0.0, o - low_value) for o, low_value in zip(opens, lows, strict=True)
                    )
                    output[i] = 100 * up / down if down else 0.0
            elif i >= period:
                highs = _window(high, i, period)
                lows = _window(low, i, period)
                prior_closes = _window(close, i - 1, period)
                if None not in (highs, lows, prior_closes):
                    assert highs is not None and lows is not None and prior_closes is not None
                    up = sum(max(0.0, h - p) for h, p in zip(highs, prior_closes, strict=True))
                    down = sum(
                        max(0.0, p - low_value)
                        for p, low_value in zip(prior_closes, lows, strict=True)
                    )
                    output[i] = 100 * up / down if down else 0.0
        elif name == "pretty_good_oscillator":
            mean, smoothed = close_sma[i], smooth_atr[i]
            if c is not None and mean is not None and smoothed is not None:
                output[i] = (c - mean) / smoothed if smoothed else 0.0
    return tuple(output)
