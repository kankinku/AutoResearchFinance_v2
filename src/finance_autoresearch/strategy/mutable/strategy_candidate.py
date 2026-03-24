import pandas as pd

from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition


def build_strategy(context: StrategyContext) -> StrategyDefinition:
    fast_window = 20
    slow_window = 50

    regime = context.regimes.classify_ema200_regime(context.close)
    bull = context.regimes.is_bull(context.close)
    bear = context.regimes.is_bear(context.close)

    fast_ema = context.indicators.ema(context.close, fast_window)
    slow_ema = context.indicators.ema(context.close, slow_window)

    fast_above_slow = fast_ema > slow_ema
    fast_below_slow = fast_ema < slow_ema
    crossed_above = fast_above_slow & ~fast_above_slow.shift(1, fill_value=False)
    crossed_below = fast_below_slow & ~fast_below_slow.shift(1, fill_value=False)

    long_entries = bull & crossed_above
    long_exits = bear | crossed_below
    short_entries = bear & crossed_below
    short_exits = bull | crossed_above

    return StrategyDefinition(
        long_entries=long_entries,
        long_exits=long_exits,
        short_entries=short_entries,
        short_exits=short_exits,
        regime=regime,
        params={
            "fast_window": fast_window,
            "slow_window": slow_window,
            "regime_window": 200,
            "symbol": context.symbol,
            "timeframe": context.timeframe,
        },
        diagnostics={
            "fast_ema": fast_ema,
            "slow_ema": slow_ema,
            "bull_bars": int(bull.sum()),
            "bear_bars": int(bear.sum()),
        },
    )
