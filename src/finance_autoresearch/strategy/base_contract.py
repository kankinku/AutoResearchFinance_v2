from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

import pandas as pd

from finance_autoresearch.strategy import indicator_registry, regime_registry

ParamValue: TypeAlias = int | float | bool | str
DiagnosticValue: TypeAlias = pd.Series | int | float | str


@dataclass(slots=True, frozen=True)
class IndicatorRegistry:
    def ema(self, series: pd.Series, window: int) -> pd.Series:
        return indicator_registry.ema(series, window)

    def sma(self, series: pd.Series, window: int) -> pd.Series:
        return indicator_registry.sma(series, window)

    def rsi(self, close: pd.Series, window: int = 14) -> pd.Series:
        return indicator_registry.rsi(close, window=window)

    def atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 14,
    ) -> pd.Series:
        return indicator_registry.atr(high, low, close, window=window)

    def rolling_std(self, series: pd.Series, window: int) -> pd.Series:
        return indicator_registry.rolling_std(series, window)

    def xaverage(self, series: pd.Series, window: int) -> pd.Series:
        return indicator_registry.xaverage(series, window)

    def macd(
        self,
        series: pd.Series,
        fast_window: int = 12,
        slow_window: int = 26,
    ) -> pd.Series:
        return indicator_registry.macd(
            series,
            fast_window=fast_window,
            slow_window=slow_window,
        )

    def macd_signal(
        self,
        series: pd.Series,
        fast_window: int = 12,
        slow_window: int = 26,
        signal_window: int = 9,
    ) -> pd.Series:
        return indicator_registry.macd_signal(
            series,
            fast_window=fast_window,
            slow_window=slow_window,
            signal_window=signal_window,
        )

    def macd_hist(
        self,
        series: pd.Series,
        fast_window: int = 12,
        slow_window: int = 26,
        signal_window: int = 9,
    ) -> pd.Series:
        return indicator_registry.macd_hist(
            series,
            fast_window=fast_window,
            slow_window=slow_window,
            signal_window=signal_window,
        )

    def rolling_corr(self, left: pd.Series, right: pd.Series, window: int) -> pd.Series:
        return indicator_registry.rolling_corr(left, right, window)

    def simple_return(self, series: pd.Series) -> pd.Series:
        return indicator_registry.simple_return(series)

    def log_return(self, series: pd.Series) -> pd.Series:
        return indicator_registry.log_return(series)


@dataclass(slots=True, frozen=True)
class RegimeRegistry:
    def classify_ema200_regime(self, close: pd.Series) -> pd.Series:
        return regime_registry.classify_ema200_regime(close)

    def is_bull(self, close: pd.Series) -> pd.Series:
        return regime_registry.is_bull(close)

    def is_bear(self, close: pd.Series) -> pd.Series:
        return regime_registry.is_bear(close)


@dataclass(slots=True, frozen=True)
class StrategyContext:
    open: pd.Series
    high: pd.Series
    low: pd.Series
    close: pd.Series
    volume: pd.Series
    symbol: str
    timeframe: str
    indicators: IndicatorRegistry
    regimes: RegimeRegistry


@dataclass(slots=True, frozen=True)
class StrategyDefinition:
    long_entries: pd.Series
    long_exits: pd.Series
    short_entries: pd.Series
    short_exits: pd.Series
    regime: pd.Series
    params: dict[str, ParamValue]
    diagnostics: dict[str, DiagnosticValue]


DEFAULT_INDICATORS = IndicatorRegistry()
DEFAULT_REGIMES = RegimeRegistry()
