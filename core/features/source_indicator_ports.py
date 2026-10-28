"""Causal, independent Python ports of non-duplicate MIT indicator formulas.

Reference inventory: pandas-ta-classic (MIT), pinned in the V3 import report.
These use completed OHLC bars only; none of the signals carry orders or alpha claims.
Candles use explicitly simplified geometry, not claimed TA-Lib numerical parity.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import fmean, pstdev

NumberSeries = Sequence[float | None]

_NUMERIC = frozenset({
    "choppiness_index", "squeeze_on", "chandelier_exit_long",
    "awesome_oscillator", "kst", "coppock_curve", "efficiency_ratio",
    "vertical_horizontal_filter", "correlation_trend_indicator", "balance_of_power",
})
_CANDLE = frozenset({
    "harami", "piercing_pattern", "dark_cloud_cover", "three_white_soldiers",
    "three_black_crows", "spinning_top", "dragonfly_doji", "gravestone_doji",
})
SOURCE_PORTS = _NUMERIC | _CANDLE


def _as_float(value: float | int | str | bool | None) -> float:
    if value is None:
        raise ValueError("missing numeric input")
    return float(value)


def _window(v: NumberSeries, index: int, length: int) -> list[float] | None:
    if index < length - 1:
        return None
    values = v[index - length + 1:index + 1]
    if any(x is None or not math.isfinite(_as_float(x)) for x in values):
        return None
    return [_as_float(x) for x in values]


def _tr(high: NumberSeries, low: NumberSeries, close: NumberSeries, index: int) -> float | None:
    if high[index] is None or low[index] is None or (index and close[index - 1] is None):
        return None
    high_value, low_value = _as_float(high[index]), _as_float(low[index])
    if high_value < low_value:
        return None
    if index == 0:
        return high_value - low_value
    previous = _as_float(close[index - 1])
    return max(high_value - low_value, abs(high_value - previous), abs(low_value - previous))


def _roc(close: NumberSeries, index: int, lag: int) -> float | None:
    if index < lag or close[index] is None or close[index - lag] in (None, 0):
        return None
    return 100.0 * (_as_float(close[index]) / _as_float(close[index - lag]) - 1.0)


def _ma_roc(close: NumberSeries, index: int, lag: int, smooth: int) -> float | None:
    values = [_roc(close, j, lag) for j in range(index - smooth + 1, index + 1)]
    if len(values) != smooth or any(x is None for x in values):
        return None
    return fmean(_as_float(x) for x in values if x is not None)


def _candle(
    name: str,
    series: Mapping[str, NumberSeries],
) -> tuple[float | None, ...]:
    op, hi, lo, cl = (series[k] for k in ("open", "high", "low", "close"))
    output: list[float | None] = [None] * len(cl)
    for i in range(len(cl)):
        needed = range(max(0, i - (2 if name.startswith("three_") else 1)), i + 1)
        if any(
            v[j] is None or not math.isfinite(_as_float(v[j]))
            for j in needed for v in (op, hi, lo, cl)
        ):
            continue
        if any(
            _as_float(hi[j]) < max(_as_float(op[j]), _as_float(cl[j]))
            or _as_float(lo[j]) > min(_as_float(op[j]), _as_float(cl[j]))
            for j in needed
        ):
            continue
        opening, high, low, close = (_as_float(v[i]) for v in (op, hi, lo, cl))
        span, body = high - low, abs(close - opening)
        signal = 0.0
        if name == "spinning_top":
            signal = _as_float(span > 0 and body <= span * 0.25
                           and high - max(opening, close) >= span * 0.2
                           and min(opening, close) - low >= span * 0.2)
        elif name == "dragonfly_doji":
            signal = _as_float(span > 0 and body <= span * 0.1
                           and high - max(opening, close) <= span * 0.1
                           and min(opening, close) - low >= span * 0.7)
        elif name == "gravestone_doji":
            signal = -_as_float(span > 0 and body <= span * 0.1
                            and min(opening, close) - low <= span * 0.1
                            and high - max(opening, close) >= span * 0.7)
        elif name in {"three_white_soldiers", "three_black_crows"}:
            if i < 2:
                continue
            direction = 1 if name == "three_white_soldiers" else -1
            signal = direction * _as_float(
                all((_as_float(cl[j]) - _as_float(op[j])) * direction > 0
                    for j in range(i - 2, i + 1))
                and all((_as_float(cl[j]) - _as_float(cl[j - 1])) * direction > 0
                        for j in (i - 1, i))
                and all((_as_float(op[j]) - _as_float(op[j - 1])) * direction > 0
                        for j in (i - 1, i))
            )
        else:
            if i == 0:
                continue
            prev_o, prev_c, prev_h, prev_l = (
                _as_float(op[i - 1]), _as_float(cl[i - 1]),
                _as_float(hi[i - 1]), _as_float(lo[i - 1]),
            )
            prev_body = abs(prev_c - prev_o)
            if name == "harami":
                inside = (
                    min(prev_o, prev_c) <= min(opening, close)
                    and max(opening, close) <= max(prev_o, prev_c)
                )
                signal = _as_float(
                    inside and prev_body > 0 and body <= prev_body * 0.5
                    and close > opening and prev_c < prev_o
                ) - _as_float(
                    inside and prev_body > 0 and body <= prev_body * 0.5
                    and close < opening and prev_c > prev_o
                )
            elif name == "piercing_pattern":
                signal = _as_float(
                    prev_c < prev_o and close > opening and opening < prev_l
                    and (prev_c + prev_o) / 2 < close < prev_o
                )
            elif name == "dark_cloud_cover":
                signal = -_as_float(
                    prev_c > prev_o and close < opening and opening > prev_h
                    and prev_o < close < (prev_c + prev_o) / 2
                )
        output[i] = signal
    return tuple(output)


def calculate_source_port(
    name: str, series: Mapping[str, NumberSeries], period: int,
    parameters: Mapping[str, int | float | str | bool]
) -> tuple[float | None, ...]:
    """Return bar-aligned, historical-only scalars, with None during warm-up."""
    if name not in SOURCE_PORTS:
        raise ValueError("unknown source port")
    if not 1 <= period <= 252:
        raise ValueError("period outside bounded range")
    if name in _CANDLE:
        return _candle(name, series)
    size = len(next(iter(series.values())))
    result: list[float | None] = [None] * size
    close = series.get("close", ())
    high = series.get("high", ())
    low = series.get("low", ())
    opened = series.get("open", ())
    for i in range(size):
        if name == "balance_of_power":
            row = (opened[i], high[i], low[i], close[i])
            if any(v is None for v in row):
                continue
            span = _as_float(high[i]) - _as_float(low[i])
            result[i] = (_as_float(close[i]) - _as_float(opened[i])) / span if span > 0 else 0.0
        elif name == "efficiency_ratio":
            window = _window(close, i, period + 1)
            if window is not None:
                movement = sum(abs(b - a) for a, b in zip(window, window[1:], strict=False))
                result[i] = abs(window[-1] - window[0]) / movement if movement else 0.0
        elif name == "vertical_horizontal_filter":
            window = _window(close, i, period + 1)
            if window is not None:
                movement = sum(abs(b - a) for a, b in zip(window, window[1:], strict=False))
                result[i] = (
                    (max(window[1:]) - min(window[1:])) / movement if movement else 0.0
                )
        elif name == "correlation_trend_indicator":
            window = _window(close, i, period)
            if window is not None and period >= 2:
                mean_y = fmean(window)
                numerator = sum((j - (period - 1) / 2) * (v - mean_y)
                                for j, v in enumerate(window))
                sqx = sum((j - (period - 1) / 2) ** 2 for j in range(period))
                sqy = sum((v - mean_y) ** 2 for v in window)
                result[i] = numerator / math.sqrt(sqx * sqy) if sqy else 0.0
        elif name == "awesome_oscillator":
            fast = int(parameters.get("fast", 5))
            if not 1 <= fast < period:
                raise ValueError("awesome oscillator fast must be < slow")
            hw, lw = _window(high, i, period), _window(low, i, period)
            if hw is not None and lw is not None:
                midpoint = [(h + low_value) / 2 for h, low_value in zip(hw, lw, strict=True)]
                result[i] = fmean(midpoint[-fast:]) - fmean(midpoint)
        elif name == "choppiness_index":
            if period < 2 or i < period:
                continue
            hw, lw = _window(high, i, period), _window(low, i, period)
            tr_values = [_tr(high, low, close, j) for j in range(i - period + 1, i + 1)]
            if hw is None or lw is None or any(x is None for x in tr_values):
                continue
            spread = max(hw) - min(lw)
            tr_sum = sum(_as_float(v) for v in tr_values if v is not None)
            result[i] = (
                100 * math.log10(tr_sum / spread) / math.log10(period)
                if spread > 0 and tr_sum > 0 else 0.0
            )
        elif name == "squeeze_on":
            if period < 2:
                continue
            hw, lw, cw = (_window(x, i, period) for x in (high, low, close))
            true_ranges = [_tr(high, low, close, j) for j in range(i - period + 1, i + 1)]
            if hw is None or lw is None or cw is None or any(x is None for x in true_ranges):
                continue
            bb_mult = _as_float(parameters.get("bb_mult", 2.0))
            kc_mult = _as_float(parameters.get("kc_mult", 1.5))
            if not (0 < bb_mult <= 10 and 0 < kc_mult <= 10):
                raise ValueError("invalid squeeze multiplier")
            basis = fmean(cw)
            width = bb_mult * pstdev(cw)
            kc_base = fmean(
                (h + low_value + c) / 3
                for h, low_value, c in zip(hw, lw, cw, strict=True)
            )
            kc_width = kc_mult * fmean(_as_float(x) for x in true_ranges if x is not None)
            result[i] = _as_float(
                basis - width > kc_base - kc_width
                and basis + width < kc_base + kc_width
            )
        elif name == "chandelier_exit_long":
            hw = _window(high, i, period)
            true_ranges = [_tr(high, low, close, j) for j in range(i - period + 1, i + 1)]
            if hw is None or any(x is None for x in true_ranges):
                continue
            mult = _as_float(parameters.get("atr_multiplier", 3.0))
            if not 0 < mult <= 20:
                raise ValueError("invalid chandelier multiplier")
            result[i] = max(hw) - mult * fmean(_as_float(v) for v in true_ranges if v is not None)
        elif name == "kst":
            intervals = (
                (max(1, round(period * 10 / 30)), max(1, round(period * 10 / 30)), 1),
                (max(1, round(period * 15 / 30)), max(1, round(period * 10 / 30)), 2),
                (max(1, round(period * 20 / 30)), max(1, round(period * 10 / 30)), 3),
                (period, max(1, round(period * 15 / 30)), 4),
            )
            kst_components = [_ma_roc(close, i, lag, smooth) for lag, smooth, _ in intervals]
            if all(component is not None for component in kst_components):
                result[i] = sum(
                    _as_float(component) * weight
                    for component, (_, _, weight) in zip(kst_components, intervals, strict=True)
                    if component is not None
                )
        elif name == "coppock_curve":
            fast = int(parameters.get("fast", 11))
            slow = int(parameters.get("slow", 14))
            smooth = int(parameters.get("smoothing", 10))
            if not (1 <= fast <= 252 and 1 <= slow <= 252 and 1 <= smooth <= 252):
                raise ValueError("invalid coppock parameters")
            components: list[float] = []
            for j in range(i - smooth + 1, i + 1):
                a, b = _roc(close, j, fast), _roc(close, j, slow)
                if a is None or b is None:
                    break
                components.append(a + b)
            if len(components) == smooth:
                result[i] = sum((k + 1) * x for k, x in enumerate(components)) / (
                    smooth * (smooth + 1) / 2
                )
    return tuple(result)
