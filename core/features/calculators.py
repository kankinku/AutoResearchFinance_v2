from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import fmean, pstdev

from core.features.contracts import FeatureSpec


class FeatureCalculationError(ValueError):
    """Raised when a registered feature cannot be calculated for the inputs."""


NumberSeries = Sequence[float | None]


def calculate_feature(
    spec: FeatureSpec, inputs: Mapping[str, NumberSeries]
) -> tuple[float | None, ...]:
    """Calculate one feature without reading outside the supplied observations."""

    series = _validate_inputs(spec, inputs)
    calculator = spec.calculator.lower()
    if calculator == "sma":
        return _single_rolling(series[0], spec.lookback, fmean)
    if calculator == "ema":
        return _ema(series[0], spec.lookback)
    if calculator == "rsi":
        return _rsi(series[0], spec.lookback)
    if calculator == "returns":
        return _returns(series[0], spec.lookback)
    if calculator == "spread":
        return _spread(series[0], series[1])
    if calculator == "rolling_correlation":
        return _rolling_correlation(series[0], series[1], spec.lookback)
    if calculator == "rolling_volatility":
        return _single_rolling(series[0], spec.lookback, pstdev)
    if calculator == "rolling_zscore":
        return _rolling_zscore(series[0], spec.lookback)
    if calculator == "percentile":
        return _percentile(series[0], spec.lookback)
    if calculator == "macd":
        return _macd(series[0], spec)
    if calculator == "atr":
        return _atr(series[0], series[1], series[2], spec.lookback)
    if calculator == "adx":
        return _adx(series[0], series[1], series[2], spec.lookback)
    if calculator == "bollinger":
        return _bollinger(series[0], spec)
    if calculator == "volume_breakout":
        return _volume_breakout(series[0], spec.lookback)
    if calculator == "52_week_high":
        return _rolling_high_ratio(series[0], spec.lookback)
    if calculator == "volatility_filter":
        return _volatility_filter(series[0], spec.lookback)
    if calculator == "regime_filter":
        return _regime_filter(series[0], spec.lookback)
    raise FeatureCalculationError(f"unsupported calculator {spec.calculator!r}")


def _validate_inputs(
    spec: FeatureSpec, inputs: Mapping[str, NumberSeries]
) -> tuple[NumberSeries, ...]:
    missing = [name for name in spec.inputs if name not in inputs]
    if missing:
        raise FeatureCalculationError(f"missing input: {missing[0]}")
    series = tuple(inputs[name] for name in spec.inputs)
    if not series or any(len(values) != len(series[0]) for values in series[1:]):
        raise FeatureCalculationError("feature inputs must have equal lengths")
    return series


def _single_rolling(
    values: NumberSeries, period: int, reducer: object
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        if any(value is None for value in window):
            continue
        numeric = [float(value) for value in window if value is not None]
        result[index] = float(reducer(numeric))  # type: ignore[operator]
    return tuple(result)


def _ema(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    initial = values[:period]
    if any(value is None for value in initial):
        return tuple(result)
    current = fmean(float(value) for value in initial if value is not None)
    result[period - 1] = current
    alpha = 2.0 / (period + 1)
    for index in range(period, len(values)):
        value = values[index]
        if value is None:
            current = math.nan
            result[index] = None
            continue
        if not math.isfinite(current):
            current = float(value)
        else:
            current += alpha * (float(value) - current)
        result[index] = current
    return tuple(result)


def _rsi(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        window = values[index - period : index + 1]
        if any(value is None for value in window):
            continue
        numeric = [float(value) for value in window if value is not None]
        gains = [max(0.0, numeric[pos + 1] - numeric[pos]) for pos in range(period)]
        losses = [max(0.0, numeric[pos] - numeric[pos + 1]) for pos in range(period)]
        average_loss = fmean(losses)
        result[index] = 100.0 if average_loss == 0 else 100.0 - 100.0 / (
            1.0 + fmean(gains) / average_loss
        )
    return tuple(result)


def _returns(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        previous, current = values[index - period], values[index]
        if previous is not None and current is not None and previous != 0:
            result[index] = float(current) / float(previous) - 1.0
    return tuple(result)


def _spread(first: NumberSeries, second: NumberSeries) -> tuple[float | None, ...]:
    return tuple(
        None if left is None or right is None else float(left) - float(right)
        for left, right in zip(first, second, strict=True)
    )


def _rolling_correlation(
    first: NumberSeries, second: NumberSeries, period: int
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(first)
    for index in range(period - 1, len(first)):
        left = first[index - period + 1 : index + 1]
        right = second[index - period + 1 : index + 1]
        if any(value is None for value in (*left, *right)):
            continue
        left_values = [float(value) for value in left if value is not None]
        right_values = [float(value) for value in right if value is not None]
        left_dev = pstdev(left_values)
        right_dev = pstdev(right_values)
        if left_dev == 0 or right_dev == 0:
            result[index] = 0.0
            continue
        left_mean, right_mean = fmean(left_values), fmean(right_values)
        covariance = fmean(
            (left_value - left_mean) * (right_value - right_mean)
            for left_value, right_value in zip(left_values, right_values, strict=True)
        )
        result[index] = covariance / (left_dev * right_dev)
    return tuple(result)


def _rolling_zscore(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        if any(value is None for value in window):
            continue
        numeric = [float(value) for value in window if value is not None]
        deviation = pstdev(numeric)
        result[index] = 0.0 if deviation == 0 else (numeric[-1] - fmean(numeric)) / deviation
    return tuple(result)


def _percentile(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        current = values[index]
        if current is None or any(value is None for value in window):
            continue
        numeric = [float(value) for value in window if value is not None]
        result[index] = sum(value <= float(current) for value in numeric) / len(numeric)
    return tuple(result)


def _macd(values: NumberSeries, spec: FeatureSpec) -> tuple[float | None, ...]:
    fast_period = int(spec.parameters.get("fast_period", max(2, spec.lookback // 2)))
    slow_period = int(spec.parameters.get("slow_period", spec.lookback))
    if fast_period >= slow_period:
        raise FeatureCalculationError("macd fast_period must be smaller than slow_period")
    fast = _ema(values, fast_period)
    slow = _ema(values, slow_period)
    return tuple(
        None if fast_value is None or slow_value is None else fast_value - slow_value
        for fast_value, slow_value in zip(fast, slow, strict=True)
    )


def _atr(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, period: int
) -> tuple[float | None, ...]:
    true_ranges: list[float | None] = [None] * len(closes)
    for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
        if high is None or low is None:
            continue
        if index == 0 or closes[index - 1] is None:
            true_ranges[index] = float(high) - float(low)
            continue
        previous_close_value = closes[index - 1]
        if previous_close_value is None:
            continue
        previous_close = float(previous_close_value)
        true_ranges[index] = max(
            float(high) - float(low),
            abs(float(high) - previous_close),
            abs(float(low) - previous_close),
        )
    return _single_rolling(tuple(true_ranges), period, fmean)


def _adx(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, period: int
) -> tuple[float | None, ...]:
    true_ranges: list[float | None] = [None] * len(closes)
    plus_moves: list[float | None] = [None] * len(closes)
    minus_moves: list[float | None] = [None] * len(closes)
    for index in range(1, len(closes)):
        high, low = highs[index], lows[index]
        previous_high, previous_low, previous_close = (
            highs[index - 1],
            lows[index - 1],
            closes[index - 1],
        )
        if any(value is None for value in (high, low, previous_high, previous_low, previous_close)):
            continue
        assert high is not None
        assert low is not None
        assert previous_high is not None
        assert previous_low is not None
        assert previous_close is not None
        high_value, low_value = float(high), float(low)
        prev_high, prev_low, prev_close = (
            float(previous_high),
            float(previous_low),
            float(previous_close),
        )
        true_ranges[index] = max(
            high_value - low_value,
            abs(high_value - prev_close),
            abs(low_value - prev_close),
        )
        up_move = high_value - prev_high
        down_move = prev_low - low_value
        plus_moves[index] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_moves[index] = down_move if down_move > up_move and down_move > 0 else 0.0
    average_true_range = _single_rolling(tuple(true_ranges), period, fmean)
    average_plus = _single_rolling(tuple(plus_moves), period, fmean)
    average_minus = _single_rolling(tuple(minus_moves), period, fmean)
    directional: list[float | None] = [None] * len(closes)
    for index, (atr, plus, minus) in enumerate(
        zip(average_true_range, average_plus, average_minus, strict=True)
    ):
        if atr is None or atr == 0 or plus is None or minus is None:
            continue
        plus_di = 100.0 * plus / atr
        minus_di = 100.0 * minus / atr
        denominator = plus_di + minus_di
        directional[index] = (
            0.0 if denominator == 0 else abs(plus_di - minus_di) / denominator * 100.0
        )
    return _single_rolling(tuple(directional), period, fmean)


def _bollinger(values: NumberSeries, spec: FeatureSpec) -> tuple[float | None, ...]:
    band = str(spec.parameters.get("band", "middle")).lower()
    deviations = float(spec.parameters.get("deviations", 2.0))
    result: list[float | None] = [None] * len(values)
    for index in range(spec.lookback - 1, len(values)):
        window = values[index - spec.lookback + 1 : index + 1]
        if any(value is None for value in window):
            continue
        numeric = [float(value) for value in window if value is not None]
        middle = fmean(numeric)
        spread = pstdev(numeric) * deviations
        if band == "upper":
            result[index] = middle + spread
        elif band == "lower":
            result[index] = middle - spread
        elif band == "middle":
            result[index] = middle
        else:
            raise FeatureCalculationError("bollinger band must be upper, middle, or lower")
    return tuple(result)


def _volume_breakout(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        current = values[index]
        previous = values[index - period : index]
        if current is None or any(value is None for value in previous):
            continue
        baseline = fmean(float(value) for value in previous if value is not None)
        result[index] = float(current) / baseline if baseline else None
    trailing = values[period - 1] if len(values) > period else None
    if trailing is not None:
        previous = values[:period]
        if not any(value is None for value in previous):
            baseline = fmean(float(value) for value in previous if value is not None)
            result[period - 1] = float(trailing) / baseline if baseline else None
    return tuple(result)


def _rolling_high_ratio(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        current = values[index]
        if current is None or any(value is None for value in window):
            continue
        highest = max(float(value) for value in window if value is not None)
        result[index] = float(current) / highest if highest else None
    return tuple(result)


def _volatility_filter(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    returns = _returns(values, 1)
    return _single_rolling(returns, period, pstdev)


def _regime_filter(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    fast_period = max(2, period // 2)
    fast = _ema(values, fast_period)
    slow = _ema(values, period)
    return tuple(
        None
        if fast_value is None or slow_value is None or slow_value == 0
        else fast_value / slow_value - 1.0
        for fast_value, slow_value in zip(fast, slow, strict=True)
    )
