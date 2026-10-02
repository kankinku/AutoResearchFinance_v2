from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkData:
    qqq_prices: tuple[float, ...]
    nasdaq_prices: tuple[float, ...]
    qqq_distributions: tuple[float, ...] | None = None
    nasdaq_distributions: tuple[float, ...] | None = None

    def slice(self, width: int) -> BenchmarkData:
        return BenchmarkData(
            self.qqq_prices[:width],
            self.nasdaq_prices[:width],
            self.qqq_distributions[:width] if self.qqq_distributions is not None else None,
            self.nasdaq_distributions[:width]
            if self.nasdaq_distributions is not None
            else None,
        )

    def select(self, indices: Sequence[int]) -> BenchmarkData:
        selected = tuple(indices)
        return BenchmarkData(
            tuple(self.qqq_prices[index] for index in selected),
            tuple(self.nasdaq_prices[index] for index in selected),
            (
                tuple(self.qqq_distributions[index] for index in selected)
                if self.qqq_distributions is not None
                else None
            ),
            (
                tuple(self.nasdaq_distributions[index] for index in selected)
                if self.nasdaq_distributions is not None
                else None
            ),
        )


@dataclass(frozen=True)
class BenchmarkComparison:
    strategy_total_return: float
    qqq_total_return: float
    nasdaq_total_return: float
    qqq_excess_return: float
    nasdaq_excess_return: float
    strategy_cagr: float
    qqq_cagr: float
    nasdaq_cagr: float
    qqq_cagr_delta: float
    nasdaq_cagr_delta: float
    qqq_outperformed: bool
    nasdaq_outperformed: bool


def compare_benchmarks(
    strategy_equity: Sequence[float],
    qqq_prices: Sequence[float],
    nasdaq_prices: Sequence[float],
    *,
    qqq_distributions: Sequence[float] | None = None,
    nasdaq_distributions: Sequence[float] | None = None,
    periods_per_year: float = 252,
) -> BenchmarkComparison:
    curves = (strategy_equity, qqq_prices, nasdaq_prices)
    if not strategy_equity or len({len(curve) for curve in curves}) != 1:
        raise ValueError("strategy and benchmark curves must have the same length")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    qqq_return = _total_return(qqq_prices, qqq_distributions)
    nasdaq_return = _total_return(nasdaq_prices, nasdaq_distributions)
    strategy_return = _total_return(strategy_equity)
    years = max((len(strategy_equity) - 1) / periods_per_year, 0.0)
    strategy_cagr = _cagr(strategy_return, years)
    qqq_cagr = _cagr(qqq_return, years)
    nasdaq_cagr = _cagr(nasdaq_return, years)
    return BenchmarkComparison(
        strategy_return,
        qqq_return,
        nasdaq_return,
        strategy_return - qqq_return,
        strategy_return - nasdaq_return,
        strategy_cagr,
        qqq_cagr,
        nasdaq_cagr,
        strategy_cagr - qqq_cagr,
        strategy_cagr - nasdaq_cagr,
        strategy_return > qqq_return,
        strategy_return > nasdaq_return,
    )


def _total_return(values: Sequence[float], distributions: Sequence[float] | None = None) -> float:
    if any(value <= 0 for value in values):
        raise ValueError("benchmark values must be positive")
    if distributions is not None and len(distributions) != len(values):
        raise ValueError("distributions must match benchmark length")
    units = 1.0 / values[0]
    for index, price in enumerate(values[1:], start=1):
        if distributions is not None:
            dividend = distributions[index]
            if dividend < 0:
                raise ValueError("distributions cannot be negative")
            units += units * dividend / price
    return units * values[-1] - 1.0


def _cagr(total_return: float, years: float) -> float:
    return (1.0 + total_return) ** (1.0 / years) - 1.0 if years else 0.0
