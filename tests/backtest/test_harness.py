from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd


def make_market_frame(
    *,
    symbol: str,
    timeframe: str,
    start: str,
    periods: int,
    freq: str,
    phase: float,
    trend: float,
) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=periods, freq=freq, tz="UTC")
    base = np.linspace(0.0, trend, periods)
    oscillation = np.sin(np.linspace(phase, phase + (36 * np.pi), periods)) * 8.0
    close = pd.Series(100.0 + base + oscillation, index=index, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": close - 0.3,
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "volume": pd.Series(5_000 + np.arange(periods), index=index, dtype=float),
            "symbol": symbol,
            "timeframe": timeframe,
        }
    )


def sample_market_pack() -> dict[tuple[str, str], pd.DataFrame]:
    return {
        ("QQQ", "1d"): make_market_frame(
            symbol="QQQ",
            timeframe="1d",
            start="2019-01-01",
            periods=2_000,
            freq="1D",
            phase=0.0,
            trend=30.0,
        ),
        ("IWM", "1d"): make_market_frame(
            symbol="IWM",
            timeframe="1d",
            start="2019-01-01",
            periods=2_000,
            freq="1D",
            phase=0.7,
            trend=20.0,
        ),
        ("BTC-USD", "1d"): make_market_frame(
            symbol="BTC-USD",
            timeframe="1d",
            start="2019-01-01",
            periods=2_000,
            freq="1D",
            phase=1.4,
            trend=45.0,
        ),
        ("QQQ", "2h"): make_market_frame(
            symbol="QQQ",
            timeframe="2h",
            start="2024-01-01",
            periods=6_600,
            freq="2h",
            phase=0.2,
            trend=25.0,
        ),
        ("IWM", "2h"): make_market_frame(
            symbol="IWM",
            timeframe="2h",
            start="2024-01-01",
            periods=6_600,
            freq="2h",
            phase=0.9,
            trend=18.0,
        ),
        ("BTC-USD", "2h"): make_market_frame(
            symbol="BTC-USD",
            timeframe="2h",
            start="2024-01-01",
            periods=6_600,
            freq="2h",
            phase=1.6,
            trend=35.0,
        ),
    }


def strategy_module() -> object:
    def build_strategy(context):
        fast_window = 12 if context.timeframe == "1d" else 30
        slow_window = 36 if context.timeframe == "1d" else 90
        fast = context.indicators.ema(context.close, fast_window)
        slow = context.indicators.ema(context.close, slow_window)
        regime = context.regimes.classify_ema200_regime(context.close)
        regime_valid = context.indicators.ema(context.close, 200).notna()
        bull = context.regimes.is_bull(context.close) & regime_valid
        bear = context.regimes.is_bear(context.close) & regime_valid
        fast_above = fast > slow
        fast_below = fast < slow
        crossed_above = fast_above & ~fast_above.shift(1, fill_value=False)
        crossed_below = fast_below & ~fast_below.shift(1, fill_value=False)

        from finance_autoresearch.strategy.base_contract import StrategyDefinition

        return StrategyDefinition(
            long_entries=bull & crossed_above,
            long_exits=regime_valid & (bear | crossed_below),
            short_entries=bear & crossed_below,
            short_exits=regime_valid & (bull | crossed_above),
            regime=regime,
            params={
                "fast_window": fast_window,
                "slow_window": slow_window,
                "symbol": context.symbol,
                "timeframe": context.timeframe,
            },
            diagnostics={
                "fast": fast,
                "slow": slow,
                "regime_valid": regime_valid,
            },
        )

    return SimpleNamespace(build_strategy=build_strategy)


def test_harness_returns_per_combination_and_aggregate_metrics() -> None:
    from finance_autoresearch.backtest.harness import run_backtests

    results = run_backtests(sample_market_pack(), strategy_module())

    assert "aggregate" in results
    assert ("QQQ", "1d") in results["combinations"]
    assert ("BTC-USD", "2h") in results["combinations"]
    assert set(results["combinations"][("QQQ", "1d")]["splits"]) == {
        "in_sample",
        "validation",
        "out_of_sample",
    }
    assert set(results["combinations"][("QQQ", "1d")]["regime_slices"]) == {
        "bull",
        "bear",
    }
    assert len(results["aggregate"]["out_of_sample_sharpe_values"]) == 6


def test_harness_computes_regime_slices_for_out_of_sample() -> None:
    from finance_autoresearch.backtest.harness import run_backtests

    results = run_backtests(sample_market_pack(), strategy_module())
    regime_slices = results["combinations"][("BTC-USD", "2h")]["regime_slices"]

    assert regime_slices["bull"]["window_exists"] is True
    assert regime_slices["bear"]["window_exists"] is True
    assert regime_slices["bull"]["bar_count"] >= 50
    assert regime_slices["bear"]["bar_count"] >= 50
    assert "exposure" in regime_slices["bull"]["metrics"]
    assert "trade_count" in regime_slices["bear"]["metrics"]


def test_harness_preserves_strategy_context_identity() -> None:
    from finance_autoresearch.backtest.harness import run_backtests

    results = run_backtests(sample_market_pack(), strategy_module())
    params = results["combinations"][("IWM", "2h")]["params"]

    assert params["symbol"] == "IWM"
    assert params["timeframe"] == "2h"
