from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from finance_autoresearch.strategy import indicator_registry
from finance_autoresearch.strategy.base_contract import DEFAULT_INDICATORS


def _manual_xaverage(values: list[float], window: int) -> pd.Series:
    alpha = 2.0 / (window + 1.0)
    average: float | None = None
    result: list[float] = []
    for value in values:
        if average is None:
            average = value
        else:
            average += alpha * (value - average)
        result.append(average)
    return pd.Series(result, dtype=float)


def test_xaverage_matches_finance_python_recursive_ema() -> None:
    series = pd.Series([10.0, 11.0, 13.0, 12.0, 14.0], dtype=float)

    expected = _manual_xaverage(series.tolist(), window=3)
    result = indicator_registry.xaverage(series, window=3)

    pd.testing.assert_series_equal(result, expected)


def test_macd_signal_and_hist_follow_xaverage_relationships() -> None:
    series = pd.Series([10.0, 11.0, 13.0, 12.0, 14.0, 15.0], dtype=float)

    macd_line = DEFAULT_INDICATORS.macd(series, fast_window=3, slow_window=5)
    signal = DEFAULT_INDICATORS.macd_signal(
        series,
        fast_window=3,
        slow_window=5,
        signal_window=4,
    )
    hist = DEFAULT_INDICATORS.macd_hist(
        series,
        fast_window=3,
        slow_window=5,
        signal_window=4,
    )

    expected_macd = DEFAULT_INDICATORS.xaverage(series, 3) - DEFAULT_INDICATORS.xaverage(series, 5)
    pd.testing.assert_series_equal(macd_line, expected_macd)
    pd.testing.assert_series_equal(signal, DEFAULT_INDICATORS.xaverage(macd_line, 4))
    pd.testing.assert_series_equal(hist, macd_line - signal)


def test_rsi_returns_50_for_flat_series_after_warmup() -> None:
    series = pd.Series([100.0] * 8, dtype=float)

    result = DEFAULT_INDICATORS.rsi(series, window=3)

    assert result.iloc[:3].isna().all()
    assert result.iloc[3:].eq(50.0).all()


def test_rolling_corr_returns_zero_for_constant_full_windows() -> None:
    left = pd.Series([1.0, 1.0, 1.0, 1.0], dtype=float)
    right = pd.Series([2.0, 2.0, 2.0, 2.0], dtype=float)

    result = DEFAULT_INDICATORS.rolling_corr(left, right, window=3)

    assert result.iloc[:2].isna().all()
    assert result.iloc[2:].eq(0.0).all()


def test_rolling_corr_matches_perfect_positive_relationship() -> None:
    left = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], dtype=float)
    right = pd.Series([2.0, 4.0, 6.0, 8.0, 10.0], dtype=float)

    result = DEFAULT_INDICATORS.rolling_corr(left, right, window=3)

    np.testing.assert_allclose(result.iloc[2:], 1.0)


def test_simple_and_log_return_match_formula_and_mask_zero_previous() -> None:
    series = pd.Series([100.0, 110.0, 55.0, 0.0, 10.0], dtype=float)

    simple = DEFAULT_INDICATORS.simple_return(series)
    logarithmic = DEFAULT_INDICATORS.log_return(series)

    assert math.isnan(simple.iloc[0])
    assert simple.iloc[1] == pytest.approx(0.1)
    assert simple.iloc[2] == pytest.approx(-0.5)
    assert simple.iloc[3] == pytest.approx(-1.0)
    assert math.isnan(simple.iloc[4])

    assert math.isnan(logarithmic.iloc[0])
    assert logarithmic.iloc[1] == pytest.approx(math.log(1.1))
    assert logarithmic.iloc[2] == pytest.approx(math.log(0.5))
    assert np.isneginf(logarithmic.iloc[3])
    assert math.isnan(logarithmic.iloc[4])
