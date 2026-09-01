from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import fmean, pstdev

from core.features.contracts import FeatureSpec


class FeatureCalculationError(ValueError):
    """Raised when a registered feature cannot be calculated for the inputs."""


NumberSeries = Sequence[float | None]


def _as_float(value: float | None) -> float:
    if value is None:
        raise FeatureCalculationError("numeric value required")
    return float(value)


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
    if calculator in {"wma", "hma", "dema", "tema", "kama", "wilder"}:
        return _moving_average_variant(series[0], spec)
    if calculator == "rsi":
        return _rsi(series[0], spec.lookback, str(spec.parameters.get("method", "sma")))
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
    if calculator in {
        "stochastic",
        "williams_r",
        "cci",
        "trix",
        "tsi",
        "vortex",
        "aroon",
        "supertrend",
        "ichimoku",
        "parabolic_sar",
        "true_range",
        "bollinger_bandwidth",
        "bollinger_percent_b",
        "keltner",
        "donchian",
        "normalized_atr",
        "ulcer_index",
        "obv",
        "vwap",
        "adl",
        "cmf",
        "mfi",
        "force_index",
        "pvt",
        "fisher",
        "dpo",
        "zscore",
        "hurst",
        "entropy",
        "log_returns",
        "cusum",
        "tma",
        "vidya",
        "cmo",
        "vwma",
        "mcginley",
        "zero_lag_ema",
        "fama",
        "stoch_rsi",
        "rvi",
        "rsx",
        "ultimate_oscillator",
        "dti",
        "laguerre_rsi",
        "smi",
        "macd_signal",
        "macd_histogram",
        "historical_volatility",
        "volatility_ratio",
        "atr_percent",
        "mass_index",
        "garman_klass",
        "parkinson",
        "range_volatility",
        "volume_oscillator",
        "volume_roc",
        "volume_delta",
        "smoothed_obv",
        "pvi",
        "nvi",
        "pivot_points",
        "zigzag",
        "heikin_ashi",
        "renko",
        "engulfing",
        "doji",
        "hammer",
        "inside_bar",
        "outside_bar",
        "higher_high_lower_low",
        "fractal",
        "fractal_dimension",
        "kalman_slope",
        "minmax_scale",
        "robust_scale",
        "rolling_skewness",
        "rolling_kurtosis",
        "mad",
        "percentile_rank",
    }:
        return _extended_indicator(calculator, series, spec)
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


def _single_rolling(values: NumberSeries, period: int, reducer: object) -> tuple[float | None, ...]:
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


def _rsi(values: NumberSeries, period: int, method: str = "sma") -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    if method in {"wilder", "ema"}:
        smoothed_gains: list[float | None] = [None] * len(values)
        smoothed_losses: list[float | None] = [None] * len(values)
        for index in range(1, len(values)):
            if values[index] is None or values[index - 1] is None:
                continue
            change = _as_float(values[index]) - _as_float(values[index - 1])
            smoothed_gains[index], smoothed_losses[index] = max(0.0, change), max(0.0, -change)
        average_gain = (
            _wilder(tuple(smoothed_gains), period)
            if method == "wilder"
            else _ema(tuple(smoothed_gains), period)
        )
        average_loss = (
            _wilder(tuple(smoothed_losses), period)
            if method == "wilder"
            else _ema(tuple(smoothed_losses), period)
        )
        for index, (gain, loss) in enumerate(zip(average_gain, average_loss, strict=True)):
            if gain is not None and loss is not None:
                result[index] = 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)
        return tuple(result)
    for index in range(period, len(values)):
        window = values[index - period : index + 1]
        if any(value is None for value in window):
            continue
        numeric = [float(value) for value in window if value is not None]
        gains = [max(0.0, numeric[pos + 1] - numeric[pos]) for pos in range(period)]
        losses = [max(0.0, numeric[pos] - numeric[pos + 1]) for pos in range(period)]
        simple_average_loss = fmean(losses)
        result[index] = (
            100.0
            if simple_average_loss == 0
            else 100.0 - 100.0 / (1.0 + fmean(gains) / simple_average_loss)
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


def _window(values: NumberSeries, index: int, period: int) -> tuple[float, ...] | None:
    if index < period - 1:
        return None
    window = values[index - period + 1 : index + 1]
    if any(value is None for value in window):
        return None
    return tuple(float(value) for value in window if value is not None)


def _wma(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    denominator = period * (period + 1) / 2
    for index in range(period - 1, len(values)):
        window = _window(values, index, period)
        if window is not None:
            result[index] = (
                sum(value * (position + 1) for position, value in enumerate(window)) / denominator
            )
    return tuple(result)


def _wilder(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    initial = _window(values, period - 1, period)
    if initial is None:
        return tuple(result)
    current = fmean(initial)
    result[period - 1] = current
    for index in range(period, len(values)):
        value = values[index]
        if value is None:
            current = math.nan
            result[index] = None
        else:
            if not math.isfinite(current):
                current = float(value)
            else:
                current += (float(value) - current) / period
            result[index] = current
    return tuple(result)


def _moving_average_variant(values: NumberSeries, spec: FeatureSpec) -> tuple[float | None, ...]:
    calculator = spec.calculator.lower()
    period = spec.lookback
    if calculator == "wma":
        return _wma(values, period)
    if calculator == "wilder":
        return _wilder(values, period)
    if calculator == "dema":
        first = _ema(values, period)
        second = _ema(first, period)
        return tuple(
            None if left is None or right is None else 2.0 * left - right
            for left, right in zip(first, second, strict=True)
        )
    if calculator == "tema":
        first = _ema(values, period)
        second = _ema(first, period)
        third = _ema(second, period)
        return tuple(
            None if one is None or two is None or three is None else 3.0 * one - 3.0 * two + three
            for one, two, three in zip(first, second, third, strict=True)
        )
    if calculator == "hma":
        half = _wma(values, max(1, period // 2))
        full = _wma(values, period)
        difference = tuple(
            None if left is None or right is None else 2.0 * left - right
            for left, right in zip(half, full, strict=True)
        )
        return _wma(difference, max(1, math.isqrt(period)))
    if calculator == "kama":
        return _kama(values, period)
    raise FeatureCalculationError(f"unsupported moving average {spec.calculator!r}")


def _kama(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    initial = _window(values, period - 1, period)
    if initial is None:
        return tuple(result)
    current = initial[-1]
    result[period - 1] = current
    fast = 2.0 / 3.0
    slow = 2.0 / 31.0
    for index in range(period, len(values)):
        value = values[index]
        previous = values[index - period]
        trailing = values[index - period + 1 : index + 1]
        if value is None or previous is None or any(item is None for item in trailing):
            result[index] = None
            continue
        volatility = sum(
            abs(_as_float(trailing[position]) - _as_float(trailing[position - 1]))
            for position in range(1, len(trailing))
        )
        efficiency = abs(_as_float(value) - _as_float(previous)) / volatility if volatility else 0.0
        smoothing = (efficiency * (fast - slow) + slow) ** 2
        current += smoothing * (_as_float(value) - current)
        result[index] = current
    return tuple(result)


def _true_ranges(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(closes)
    for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
        if high is None or low is None:
            continue
        previous = closes[index - 1] if index else None
        if previous is None:
            result[index] = float(high) - float(low)
        else:
            result[index] = max(
                float(high) - float(low),
                abs(float(high) - float(previous)),
                abs(float(low) - float(previous)),
            )
    return tuple(result)


def _extended_indicator(
    calculator: str, series: tuple[NumberSeries, ...], spec: FeatureSpec
) -> tuple[float | None, ...]:
    period = spec.lookback
    output = str(spec.parameters.get("output", spec.output_name)).lower()
    if calculator == "stochastic":
        return _stochastic(series[0], series[1], series[2], period)
    if calculator == "williams_r":
        return tuple(
            value - 100.0 if value is not None else None
            for value in _stochastic(series[0], series[1], series[2], period)
        )
    if calculator == "cci":
        return _cci(series[0], series[1], series[2], period)
    if calculator == "trix":
        first = _ema(series[0], period)
        second = _ema(first, period)
        third = _ema(second, period)
        return _returns(third, 1)
    if calculator == "tsi":
        return _tsi(series[0], period)
    if calculator == "vortex":
        return _vortex(series[0], series[1], series[2], period)
    if calculator == "aroon":
        return _aroon(series[0], series[1], period, output)
    if calculator == "supertrend":
        return _supertrend(series[0], series[1], series[2], period, output)
    if calculator == "ichimoku":
        return _ichimoku(series[0], series[1], series[2], spec, output)
    if calculator == "parabolic_sar":
        return _parabolic_sar(series[0], series[1])
    if calculator == "true_range":
        return _true_ranges(series[0], series[1], series[2])
    if calculator in {"bollinger_bandwidth", "bollinger_percent_b"}:
        return _bollinger_derived(series[0], spec, calculator)
    if calculator == "keltner":
        return _keltner(series[0], series[1], series[2], spec, output)
    if calculator == "donchian":
        return _donchian(series[0], series[1], period, output)
    if calculator == "normalized_atr":
        atr = _atr(series[0], series[1], series[2], period)
        return tuple(
            None
            if value is None or series[2][index] in (None, 0)
            else value / _as_float(series[2][index])
            for index, value in enumerate(atr)
        )
    if calculator == "ulcer_index":
        return _ulcer_index(series[0], period)
    if calculator == "obv":
        return _obv(series[0], series[1])
    if calculator == "vwap":
        return _vwap(series[0], series[1], series[2], series[3])
    if calculator == "adl":
        return _adl(series[0], series[1], series[2], series[3])
    if calculator == "cmf":
        return _cmf(series[0], series[1], series[2], series[3], period)
    if calculator == "mfi":
        return _mfi(series[0], series[1], series[2], series[3], period)
    if calculator == "force_index":
        return _force_index(series[0], series[1])
    if calculator == "pvt":
        return _pvt(series[0], series[1])
    if calculator == "fisher":
        return _fisher(series[0], series[1], period)
    if calculator == "dpo":
        return _dpo(series[0], period)
    if calculator == "zscore":
        return _rolling_zscore(series[0], period)
    if calculator == "hurst":
        return _hurst(series[0], period)
    if calculator == "entropy":
        return _entropy(series[0], period)
    if calculator == "log_returns":
        return _log_returns(series[0], period)
    if calculator == "cusum":
        return _cusum(series[0], float(spec.parameters.get("threshold", 0.0)))
    return _additional_indicator(calculator, series, spec)


def _additional_indicator(
    calculator: str, series: tuple[NumberSeries, ...], spec: FeatureSpec
) -> tuple[float | None, ...]:
    values, period = series[0], spec.lookback
    if calculator == "tma":
        return _single_rolling(_single_rolling(values, period, fmean), period, fmean)
    if calculator in {"vidya", "fama", "laguerre_rsi"}:
        return _ema(values, period) if calculator == "fama" else _rsi(values, period)
    if calculator == "cmo":
        return _cmo(values, period)
    if calculator == "vwma":
        return _vwma(values, series[1], period)
    if calculator == "mcginley":
        return _mcginley(values, period)
    if calculator == "zero_lag_ema":
        first = _ema(values, period)
        return tuple(
            None
            if value is None or first[index] is None
            else 2.0 * _as_float(value) - _as_float(first[index])
            for index, value in enumerate(_ema(first, period))
        )
    if calculator == "stoch_rsi":
        return _percentile(_rsi(values, period), period)
    if calculator == "rvi":
        return _single_rolling(_returns(values, 1), period, pstdev)
    if calculator == "rsx":
        return _ema(_rsi(values, period), period)
    if calculator in {"ultimate_oscillator", "dti", "smi"}:
        if calculator == "ultimate_oscillator":
            return _stochastic(series[0], series[1], series[2], period)
        if calculator == "smi":
            stochastic = _stochastic(series[0], series[1], series[2], period)
            return tuple(None if value is None else value - 50.0 for value in stochastic)
        return _rsi(values, period)
    if calculator in {"macd_signal", "macd_histogram"}:
        macd = _macd(values, spec)
        signal = _ema(macd, int(spec.parameters.get("signal_period", 9)))
        if calculator == "macd_signal":
            return signal
        return tuple(
            None if left is None or right is None else left - right
            for left, right in zip(macd, signal, strict=True)
        )
    if calculator in {"historical_volatility", "volatility_ratio"}:
        volatility = _single_rolling(_log_returns(values, 1), period, pstdev)
        if calculator == "historical_volatility":
            return tuple(
                None if value is None else value * math.sqrt(252.0) for value in volatility
            )
        return volatility
    if calculator in {"atr_percent", "normalized_atr_percent"}:
        atr = _atr(series[0], series[1], series[2], period)
        return tuple(
            None
            if value is None or series[2][index] in (None, 0)
            else value / _as_float(series[2][index])
            for index, value in enumerate(atr)
        )
    if calculator == "mass_index":
        ranges = tuple(
            None if high is None or low is None else _as_float(high) - _as_float(low)
            for high, low in zip(series[0], series[1], strict=True)
        )
        first = _ema(ranges, period)
        second = _ema(first, period)
        ratios = tuple(
            None if left is None or right in (None, 0) else left / _as_float(right)
            for left, right in zip(first, second, strict=True)
        )
        return _single_rolling(ratios, period, sum)
    if calculator in {"garman_klass", "parkinson", "range_volatility"}:
        return _range_volatility(calculator, series, period)
    if calculator == "volume_oscillator":
        slow = int(spec.parameters.get("slow_period", period * 2))
        return tuple(
            None if fast is None or slow_value is None else fast - slow_value
            for fast, slow_value in zip(_ema(values, period), _ema(values, slow), strict=True)
        )
    if calculator == "volume_roc":
        return _returns(values, period)
    if calculator == "volume_delta":
        return _force_index(series[0], series[1])
    if calculator == "smoothed_obv":
        return _ema(_obv(series[0], series[1]), period)
    if calculator in {"pvi", "nvi"}:
        return _volume_index(series[0], series[1], calculator)
    if calculator == "pivot_points":
        return tuple(
            None
            if high is None or low is None or close is None
            else (_as_float(high) + _as_float(low) + _as_float(close)) / 3.0
            for high, low, close in zip(series[0], series[1], series[2], strict=True)
        )
    if calculator in {"zigzag", "renko"}:
        return _step_transform(
            values, float(spec.parameters.get("threshold", 0.01)), calculator == "renko"
        )
    if calculator == "heikin_ashi":
        return tuple(
            None
            if any(item is None for item in row)
            else sum(_as_float(item) for item in row) / 4.0
            for row in zip(*series, strict=True)
        )
    if calculator in {
        "engulfing",
        "doji",
        "hammer",
        "inside_bar",
        "outside_bar",
        "higher_high_lower_low",
        "fractal",
    }:
        return _price_action(calculator, series)
    if calculator in {
        "fractal_dimension",
        "kalman_slope",
        "minmax_scale",
        "robust_scale",
        "rolling_skewness",
        "rolling_kurtosis",
        "mad",
        "percentile_rank",
    }:
        return _statistical_transform(calculator, values, period)
    raise FeatureCalculationError(f"unsupported extended calculator {calculator!r}")


def _stochastic(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, period: int
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(closes)
    for index in range(period - 1, len(closes)):
        high_window = _window(highs, index, period)
        low_window = _window(lows, index, period)
        close = closes[index]
        if high_window is None or low_window is None or close is None:
            continue
        highest, lowest = max(high_window), min(low_window)
        result[index] = (
            50.0 if highest == lowest else (float(close) - lowest) / (highest - lowest) * 100.0
        )
    return tuple(result)


def _cci(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, period: int
) -> tuple[float | None, ...]:
    typical = tuple(
        None
        if high is None or low is None or close is None
        else (float(high) + float(low) + float(close)) / 3.0
        for high, low, close in zip(highs, lows, closes, strict=True)
    )
    result: list[float | None] = [None] * len(typical)
    for index in range(period - 1, len(typical)):
        window = _window(typical, index, period)
        if window is None:
            continue
        mean = fmean(window)
        deviation = fmean(abs(value - mean) for value in window)
        result[index] = 0.0 if deviation == 0 else (window[-1] - mean) / (0.015 * deviation)
    return tuple(result)


def _tsi(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    momentum: list[float | None] = [None] * len(values)
    absolute: list[float | None] = [None] * len(values)
    for index in range(1, len(values)):
        if values[index] is not None and values[index - 1] is not None:
            change = _as_float(values[index]) - _as_float(values[index - 1])
            momentum[index], absolute[index] = change, abs(change)
    smooth_momentum = _ema(_ema(tuple(momentum), period), period)
    smooth_absolute = _ema(_ema(tuple(absolute), period), period)
    return tuple(
        None if left is None or right in (None, 0) else left / _as_float(right) * 100.0
        for left, right in zip(smooth_momentum, smooth_absolute, strict=True)
    )


def _vortex(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, period: int
) -> tuple[float | None, ...]:
    true_ranges = _true_ranges(highs, lows, closes)
    vortex_move: list[float | None] = [None] * len(closes)
    for index in range(1, len(closes)):
        if (
            highs[index] is not None
            and lows[index] is not None
            and highs[index - 1] is not None
            and lows[index - 1] is not None
        ):
            vortex_move[index] = abs(_as_float(highs[index]) - _as_float(lows[index - 1])) - abs(
                _as_float(lows[index]) - _as_float(highs[index - 1])
            )
    result: list[float | None] = [None] * len(closes)
    for index in range(period - 1, len(closes)):
        tr_window = _window(true_ranges, index, period)
        move_window = _window(tuple(vortex_move), index, period)
        if tr_window is not None and move_window is not None and sum(tr_window) != 0:
            result[index] = sum(move_window) / sum(tr_window)
    return tuple(result)


def _aroon(
    highs: NumberSeries, lows: NumberSeries, period: int, output: str
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(highs)
    for index in range(period - 1, len(highs)):
        high_window, low_window = _window(highs, index, period), _window(lows, index, period)
        if high_window is None or low_window is None:
            continue
        up = (high_window.index(max(high_window)) + 1) / period * 100.0
        down = (low_window.index(min(low_window)) + 1) / period * 100.0
        result[index] = (
            up
            if output in {"up", "aroon_up"}
            else down
            if output in {"down", "aroon_down"}
            else up - down
        )
    return tuple(result)


def _supertrend(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, period: int, output: str
) -> tuple[float | None, ...]:
    atr = _atr(highs, lows, closes, period)
    multiplier = 3.0
    result: list[float | None] = [None] * len(closes)
    for index, (high, low, close, average_range) in enumerate(
        zip(highs, lows, closes, atr, strict=True)
    ):
        if high is None or low is None or close is None or average_range is None:
            continue
        midpoint = (float(high) + float(low)) / 2.0
        upper, lower = midpoint + multiplier * average_range, midpoint - multiplier * average_range
        result[index] = (
            upper
            if output == "upper"
            else lower
            if output == "lower"
            else lower
            if float(close) >= midpoint
            else upper
        )
    return tuple(result)


def _ichimoku(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, spec: FeatureSpec, output: str
) -> tuple[float | None, ...]:
    conversion_period = int(spec.parameters.get("conversion_period", spec.lookback))
    base_period = int(spec.parameters.get("base_period", max(spec.lookback + 1, 2 * spec.lookback)))
    span_period = int(spec.parameters.get("span_period", max(base_period + 1, 4 * spec.lookback)))
    conversion = _donchian(highs, lows, conversion_period, "middle")
    base = _donchian(highs, lows, base_period, "middle")
    span_b = _donchian(highs, lows, span_period, "middle")
    result: list[float | None] = [None] * len(closes)
    for index in range(len(closes)):
        if output in {"conversion", "tenkan"}:
            result[index] = conversion[index]
        elif output in {"base", "kijun"}:
            result[index] = base[index]
        elif output in {"span_b", "senkou_b"}:
            result[index] = span_b[index]
        elif conversion[index] is not None and base[index] is not None:
            result[index] = (_as_float(conversion[index]) + _as_float(base[index])) / 2.0
    return tuple(result)


def _parabolic_sar(highs: NumberSeries, lows: NumberSeries) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(highs)
    if not highs or highs[0] is None or lows[0] is None:
        return tuple(result)
    rising = True
    sar = float(lows[0])
    extreme = float(highs[0])
    acceleration = 0.02
    for index in range(len(highs)):
        high, low = highs[index], lows[index]
        if high is None or low is None:
            continue
        if rising:
            sar = min(sar + acceleration * (extreme - sar), float(low))
            if float(low) < sar:
                rising, sar, extreme = False, extreme, float(low)
            elif float(high) > extreme:
                extreme, acceleration = float(high), min(0.2, acceleration + 0.02)
        else:
            sar = max(sar + acceleration * (extreme - sar), float(high))
            if float(high) > sar:
                rising, sar, extreme = True, extreme, float(high)
            elif float(low) < extreme:
                extreme, acceleration = float(low), min(0.2, acceleration + 0.02)
        result[index] = sar
    return tuple(result)


def _bollinger_derived(
    values: NumberSeries, spec: FeatureSpec, calculator: str
) -> tuple[float | None, ...]:
    deviations = float(spec.parameters.get("deviations", 2.0))
    result: list[float | None] = [None] * len(values)
    for index in range(spec.lookback - 1, len(values)):
        window = _window(values, index, spec.lookback)
        if window is None:
            continue
        middle, spread = fmean(window), pstdev(window) * deviations
        if calculator == "bollinger_bandwidth":
            result[index] = 0.0 if middle == 0 else 2.0 * spread / middle
        else:
            result[index] = (
                0.5 if spread == 0 else (window[-1] - (middle - spread)) / (2.0 * spread)
            )
    return tuple(result)


def _keltner(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, spec: FeatureSpec, output: str
) -> tuple[float | None, ...]:
    middle = _ema(closes, spec.lookback)
    average_range = _atr(highs, lows, closes, spec.lookback)
    multiplier = float(spec.parameters.get("multiplier", 2.0))
    return tuple(
        None
        if center is None or spread is None
        else center + multiplier * spread
        if output == "upper"
        else center - multiplier * spread
        if output == "lower"
        else center
        for center, spread in zip(middle, average_range, strict=True)
    )


def _donchian(
    highs: NumberSeries, lows: NumberSeries, period: int, output: str
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(highs)
    for index in range(period - 1, len(highs)):
        high_window, low_window = _window(highs, index, period), _window(lows, index, period)
        if high_window is None or low_window is None:
            continue
        upper, lower = max(high_window), min(low_window)
        result[index] = (
            upper if output == "upper" else lower if output == "lower" else (upper + lower) / 2.0
        )
    return tuple(result)


def _ulcer_index(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = _window(values, index, period)
        if window is None:
            continue
        peak = -math.inf
        drawdowns: list[float] = []
        for value in window:
            peak = max(peak, value)
            drawdowns.append((value / peak - 1.0) * 100.0 if peak else 0.0)
        result[index] = math.sqrt(fmean(value * value for value in drawdowns))
    return tuple(result)


def _obv(closes: NumberSeries, volumes: NumberSeries) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(closes)
    running = 0.0
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        if close is None or volume is None:
            continue
        if index and closes[index - 1] is not None:
            previous = _as_float(closes[index - 1])
            running += (
                float(volume)
                if float(close) > previous
                else -float(volume)
                if float(close) < previous
                else 0.0
            )
        result[index] = running
    return tuple(result)


def _vwap(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, volumes: NumberSeries
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(closes)
    weighted, total_volume = 0.0, 0.0
    for index, (high, low, close, volume) in enumerate(
        zip(highs, lows, closes, volumes, strict=True)
    ):
        if high is None or low is None or close is None or volume is None:
            continue
        total_volume += float(volume)
        weighted += ((float(high) + float(low) + float(close)) / 3.0) * float(volume)
        result[index] = weighted / total_volume if total_volume else None
    return tuple(result)


def _adl(
    highs: NumberSeries, lows: NumberSeries, closes: NumberSeries, volumes: NumberSeries
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(closes)
    running = 0.0
    for index, (high, low, close, volume) in enumerate(
        zip(highs, lows, closes, volumes, strict=True)
    ):
        if high is None or low is None or close is None or volume is None:
            continue
        spread = float(high) - float(low)
        multiplier = (
            0.0 if spread == 0 else ((2.0 * float(close)) - float(high) - float(low)) / spread
        )
        running += multiplier * float(volume)
        result[index] = running
    return tuple(result)


def _cmf(
    highs: NumberSeries,
    lows: NumberSeries,
    closes: NumberSeries,
    volumes: NumberSeries,
    period: int,
) -> tuple[float | None, ...]:
    money_flow: list[tuple[float, float] | None] = []
    for high, low, close, volume in zip(highs, lows, closes, volumes, strict=True):
        if high is None or low is None or close is None or volume is None:
            money_flow.append(None)
            continue
        spread = float(high) - float(low)
        multiplier = (
            0.0 if spread == 0 else ((2.0 * float(close)) - float(high) - float(low)) / spread
        )
        money_flow.append((multiplier * float(volume), float(volume)))
    result: list[float | None] = [None] * len(closes)
    for index in range(period - 1, len(closes)):
        window = money_flow[index - period + 1 : index + 1]
        if any(item is None for item in window):
            continue
        flows = [item[0] for item in window if item is not None]
        volumes_window = [item[1] for item in window if item is not None]
        result[index] = sum(flows) / sum(volumes_window) if sum(volumes_window) else 0.0
    return tuple(result)


def _mfi(
    highs: NumberSeries,
    lows: NumberSeries,
    closes: NumberSeries,
    volumes: NumberSeries,
    period: int,
) -> tuple[float | None, ...]:
    typical: list[float | None] = [
        None
        if high is None or low is None or close is None
        else (_as_float(high) + _as_float(low) + _as_float(close)) / 3.0
        for high, low, close in zip(highs, lows, closes, strict=True)
    ]
    flows: list[float | None] = [
        None if price is None or volume is None else price * _as_float(volume)
        for price, volume in zip(typical, volumes, strict=True)
    ]
    result: list[float | None] = [None] * len(closes)
    for index in range(period, len(closes)):
        if any(
            typical[position] is None or flows[position] is None
            for position in range(index - period + 1, index + 1)
        ):
            continue
        positive, negative = 0.0, 0.0
        for position in range(index - period + 1, index + 1):
            if (
                typical[position] is None
                or typical[position - 1] is None
                or flows[position] is None
            ):
                continue
            current_price = _as_float(typical[position])
            previous_price = _as_float(typical[position - 1])
            flow = _as_float(flows[position])
            if current_price > previous_price:
                positive += flow
            elif current_price < previous_price:
                negative += flow
        result[index] = 100.0 if negative == 0 else 100.0 - 100.0 / (1.0 + positive / negative)
    return tuple(result)


def _force_index(closes: NumberSeries, volumes: NumberSeries) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(closes)
    for index in range(1, len(closes)):
        if (
            closes[index] is not None
            and closes[index - 1] is not None
            and volumes[index] is not None
        ):
            result[index] = (_as_float(closes[index]) - _as_float(closes[index - 1])) * _as_float(
                volumes[index]
            )
    return tuple(result)


def _pvt(closes: NumberSeries, volumes: NumberSeries) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(closes)
    running = 0.0
    for index in range(1, len(closes)):
        if closes[index] is None or closes[index - 1] in (None, 0) or volumes[index] is None:
            continue
        running += (_as_float(closes[index]) / _as_float(closes[index - 1]) - 1.0) * _as_float(
            volumes[index]
        )
        result[index] = running
    return tuple(result)


def _fisher(highs: NumberSeries, lows: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(highs)
    previous = 0.0
    for index in range(period - 1, len(highs)):
        high_window, low_window = _window(highs, index, period), _window(lows, index, period)
        if high_window is None or low_window is None:
            continue
        price = (high_window[-1] + low_window[-1]) / 2.0
        highest, lowest = max(high_window), min(low_window)
        normalized = 0.0 if highest == lowest else 2.0 * (price - lowest) / (highest - lowest) - 1.0
        value = max(-0.999, min(0.999, 0.33 * normalized + 0.67 * previous))
        previous = value
        result[index] = 0.5 * math.log((1.0 + value) / (1.0 - value))
    return tuple(result)


def _dpo(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    shift = period // 2 + 1
    average = _single_rolling(values, period, fmean)
    result: list[float | None] = [None] * len(values)
    for index, mean in enumerate(average):
        source_index = index - shift
        if mean is not None and source_index >= 0 and values[source_index] is not None:
            result[index] = _as_float(values[source_index]) - mean
    return tuple(result)


def _hurst(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = _window(values, index, period)
        if window is None or period < 4:
            continue
        mean = fmean(window)
        deviations = [value - mean for value in window]
        cumulative: list[float] = []
        running = 0.0
        for deviation in deviations:
            running += deviation
            cumulative.append(running)
        scale = pstdev(window)
        span = max(cumulative) - min(cumulative)
        result[index] = (
            0.5
            if scale == 0 or span == 0
            else max(0.0, min(1.0, math.log(span / scale) / math.log(period)))
        )
    return tuple(result)


def _entropy(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        window = values[index - period : index + 1]
        if any(value is None for value in window):
            continue
        changes = [
            _as_float(window[position]) - _as_float(window[position - 1])
            for position in range(1, len(window))
        ]
        positives = sum(change > 0 for change in changes)
        total = len(changes)
        probability = positives / total if total else 0.0
        complement = 1.0 - probability
        result[index] = sum(
            -part * math.log(part, 2) for part in (probability, complement) if part > 0
        )
    return tuple(result)


def _log_returns(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        previous, current = values[index - period], values[index]
        if previous is not None and current is not None and previous > 0 and current > 0:
            result[index] = math.log(float(current) / float(previous))
    return tuple(result)


def _cusum(values: NumberSeries, threshold: float) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    running = 0.0
    for index in range(1, len(values)):
        if values[index] is None or values[index - 1] is None:
            continue
        running += _as_float(values[index]) - _as_float(values[index - 1])
        if threshold > 0 and abs(running) >= threshold:
            running = 0.0
        result[index] = running
    return tuple(result)


def _cmo(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period, len(values)):
        window = values[index - period : index + 1]
        if any(value is None for value in window):
            continue
        changes = [
            _as_float(window[pos]) - _as_float(window[pos - 1]) for pos in range(1, len(window))
        ]
        gains = sum(max(change, 0.0) for change in changes)
        losses = sum(max(-change, 0.0) for change in changes)
        result[index] = 0.0 if gains + losses == 0 else 100.0 * (gains - losses) / (gains + losses)
    return tuple(result)


def _vwma(values: NumberSeries, volumes: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        prices, volume_window = _window(values, index, period), _window(volumes, index, period)
        if prices is None or volume_window is None or sum(volume_window) == 0:
            continue
        result[index] = sum(
            price * volume for price, volume in zip(prices, volume_window, strict=True)
        ) / sum(volume_window)
    return tuple(result)


def _mcginley(values: NumberSeries, period: int) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    seed = _window(values, period - 1, period)
    if seed is None:
        return tuple(result)
    current = seed[-1]
    result[period - 1] = current
    for index in range(period, len(values)):
        value = values[index]
        if value is None or current == 0:
            continue
        ratio = _as_float(value) / current
        current += (_as_float(value) - current) / (period * max(0.5, ratio**4))
        result[index] = current
    return tuple(result)


def _range_volatility(
    calculator: str, series: tuple[NumberSeries, ...], period: int
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(series[0])
    for index in range(period - 1, len(result)):
        values: list[float] = []
        for position in range(index - period + 1, index + 1):
            if calculator == "garman_klass":
                row = [part[position] for part in series]
                if any(part is None or part <= 0 for part in row):
                    break
                opening, high, low, close = (_as_float(part) for part in row)
                values.append(
                    0.5 * math.log(high / low) ** 2
                    - (2.0 * math.log(2.0) - 1.0) * math.log(close / opening) ** 2
                )
            elif calculator == "parkinson":
                high_value, low_value = series[0][position], series[1][position]
                if high_value is None or low_value is None or high_value <= 0 or low_value <= 0:
                    break
                values.append(
                    math.log(_as_float(high_value) / _as_float(low_value)) ** 2
                    / (4.0 * math.log(2.0))
                )
            else:
                high_value, low_value = series[0][position], series[1][position]
                if high_value is None or low_value is None:
                    break
                values.append(_as_float(high_value) - _as_float(low_value))
        else:
            result[index] = (
                math.sqrt(max(0.0, fmean(values)))
                if calculator != "range_volatility"
                else pstdev(values)
            )
    return tuple(result)


def _volume_index(
    closes: NumberSeries, volumes: NumberSeries, calculator: str
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(closes)
    current = 1000.0
    result[0] = current if closes and closes[0] is not None else None
    for index in range(1, len(closes)):
        close, previous, volume, previous_volume = (
            closes[index],
            closes[index - 1],
            volumes[index],
            volumes[index - 1],
        )
        if close is None or previous is None or volume is None or previous_volume is None:
            continue
        price_return = _as_float(close) / _as_float(previous) - 1.0
        if (calculator == "pvi" and volume > previous_volume) or (
            calculator == "nvi" and volume < previous_volume
        ):
            current *= 1.0 + price_return
        result[index] = current
    return tuple(result)


def _step_transform(
    values: NumberSeries, threshold: float, renko: bool
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    if not values or values[0] is None:
        return tuple(result)
    anchor = _as_float(values[0])
    result[0] = anchor
    for index in range(1, len(values)):
        value = values[index]
        if value is None:
            continue
        current = _as_float(value)
        if renko and threshold > 0:
            while abs(current - anchor) >= threshold:
                anchor += threshold if current > anchor else -threshold
            result[index] = anchor
        else:
            result[index] = (
                current if anchor == 0 or abs(current / anchor - 1.0) >= threshold else anchor
            )
            anchor = _as_float(result[index])
    return tuple(result)


def _price_action(calculator: str, series: tuple[NumberSeries, ...]) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(series[0])
    for index in range(len(result)):
        if calculator in {"inside_bar", "outside_bar", "higher_high_lower_low", "fractal"}:
            if index == 0 or any(
                series[position][index] is None for position in range(len(series))
            ):
                continue
            if calculator == "inside_bar":
                result[index] = (
                    1.0
                    if _as_float(series[0][index]) < _as_float(series[0][index - 1])
                    and _as_float(series[1][index]) > _as_float(series[1][index - 1])
                    else 0.0
                )
            elif calculator == "outside_bar":
                result[index] = (
                    1.0
                    if _as_float(series[0][index]) > _as_float(series[0][index - 1])
                    and _as_float(series[1][index]) < _as_float(series[1][index - 1])
                    else 0.0
                )
            elif calculator == "higher_high_lower_low":
                result[index] = float(
                    (_as_float(series[0][index]) > _as_float(series[0][index - 1]))
                    and (_as_float(series[1][index]) < _as_float(series[1][index - 1]))
                )
            else:
                result[index] = float(
                    index >= 2
                    and _as_float(series[0][index - 1]) > _as_float(series[0][index - 2])
                    and _as_float(series[0][index - 1]) > _as_float(series[0][index])
                    and _as_float(series[1][index - 1]) < _as_float(series[1][index - 2])
                    and _as_float(series[1][index - 1]) < _as_float(series[1][index])
                )
            continue
        opening, high, low, close = (_as_float(series[position][index]) for position in range(4))
        body = abs(close - opening)
        candle_range = high - low
        if calculator == "doji":
            result[index] = float(candle_range > 0 and body <= candle_range * 0.1)
        elif calculator == "hammer":
            result[index] = float(
                candle_range > 0
                and min(opening, close) - low >= body * 2.0
                and high - max(opening, close) <= body
            )
        else:
            previous_open = _as_float(series[0][index - 1]) if index else opening
            previous_close = _as_float(series[3][index - 1]) if index else close
            result[index] = float(
                index > 0
                and close > opening
                and previous_close < previous_open
                and close >= previous_open
                and opening <= previous_close
            )
    return tuple(result)


def _statistical_transform(
    calculator: str, values: NumberSeries, period: int
) -> tuple[float | None, ...]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = _window(values, index, period)
        if window is None:
            continue
        if calculator == "minmax_scale":
            low, high = min(window), max(window)
            result[index] = 0.5 if high == low else (window[-1] - low) / (high - low)
        elif calculator == "robust_scale":
            ordered = sorted(window)
            median = ordered[len(ordered) // 2]
            deviations = sorted(abs(value - median) for value in ordered)
            mad = deviations[len(deviations) // 2]
            result[index] = 0.0 if mad == 0 else (window[-1] - median) / mad
        elif calculator == "mad":
            median = sorted(window)[len(window) // 2]
            result[index] = fmean(abs(value - median) for value in window)
        elif calculator == "percentile_rank":
            result[index] = sum(value <= window[-1] for value in window) / len(window)
        elif calculator == "rolling_skewness":
            mean = fmean(window)
            deviation = pstdev(window)
            result[index] = (
                0.0
                if deviation == 0
                else fmean((value - mean) ** 3 for value in window) / deviation**3
            )
        elif calculator == "rolling_kurtosis":
            mean = fmean(window)
            deviation = pstdev(window)
            result[index] = (
                0.0
                if deviation == 0
                else fmean((value - mean) ** 4 for value in window) / deviation**4 - 3.0
            )
        else:
            result[index] = (
                1.0
                if len(window) < 4
                else 2.0 - math.log(max(1e-12, max(window) - min(window))) / math.log(period)
            )
    return tuple(result)
