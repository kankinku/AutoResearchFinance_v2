from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    average_gain = gains.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    average_loss = losses.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    relative_strength = average_gain / average_loss
    result = 100 - (100 / (1 + relative_strength))
    both_zero = average_gain.eq(0.0) & average_loss.eq(0.0)
    return result.mask(both_zero, 50.0)


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14,
) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()


def rolling_std(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).std(ddof=0)


def xaverage(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def macd(series: pd.Series, fast_window: int = 12, slow_window: int = 26) -> pd.Series:
    return xaverage(series, fast_window) - xaverage(series, slow_window)


def macd_signal(
    series: pd.Series,
    fast_window: int = 12,
    slow_window: int = 26,
    signal_window: int = 9,
) -> pd.Series:
    return xaverage(macd(series, fast_window=fast_window, slow_window=slow_window), signal_window)


def macd_hist(
    series: pd.Series,
    fast_window: int = 12,
    slow_window: int = 26,
    signal_window: int = 9,
) -> pd.Series:
    macd_line = macd(series, fast_window=fast_window, slow_window=slow_window)
    return macd_line - xaverage(macd_line, signal_window)


def rolling_corr(left: pd.Series, right: pd.Series, window: int) -> pd.Series:
    min_periods = window
    count = left.rolling(window=window, min_periods=min_periods).count()
    sum_left = left.rolling(window=window, min_periods=min_periods).sum()
    sum_right = right.rolling(window=window, min_periods=min_periods).sum()
    sum_square_left = left.pow(2).rolling(window=window, min_periods=min_periods).sum()
    sum_square_right = right.pow(2).rolling(window=window, min_periods=min_periods).sum()
    sum_cross = (left * right).rolling(window=window, min_periods=min_periods).sum()

    numerator = count * sum_cross - sum_left * sum_right
    denominator = (
        (count * sum_square_left - sum_left.pow(2))
        * (count * sum_square_right - sum_right.pow(2))
    ).pow(0.5)

    result = numerator / denominator
    zero_denominator = denominator.eq(0.0) & count.ge(2)
    return result.mask(zero_denominator, 0.0)


def simple_return(series: pd.Series) -> pd.Series:
    previous = series.shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = series / previous
    return (ratio - 1.0).where(previous.ne(0.0))


def log_return(series: pd.Series) -> pd.Series:
    previous = series.shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = series / previous
        result = pd.Series(np.log(ratio), index=series.index, dtype=float)
    return result.where(previous.ne(0.0))
