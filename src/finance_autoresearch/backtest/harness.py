from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

import pandas as pd
import vectorbt as vbt

from finance_autoresearch.backtest.data_loader import FIXED_MARKET_PACK_KEYS, MarketPack
from finance_autoresearch.backtest.scoring import (
    METRIC_NAMES,
    aggregate_metric_means,
    annualization_factor,
    compute_metrics,
    regime_window_exists,
)
from finance_autoresearch.strategy.base_contract import (
    DEFAULT_INDICATORS,
    DEFAULT_REGIMES,
    StrategyContext,
)
from finance_autoresearch.strategy.regime_registry import classify_ema200_regime

INITIAL_CASH = 100_000.0
FEES_PER_SIDE = 0.001
SLIPPAGE_PER_SIDE = 0.0005
SPLIT_WINDOWS = {
    "1d": {"in_sample": 1_095, "validation": 365, "out_of_sample": 365},
    "2h": {"in_sample": 270, "validation": 135, "out_of_sample": 135},
}


def run_backtests(
    market_pack: MarketPack,
    strategy_module: object,
    *,
    market_keys: tuple[tuple[str, str], ...] = FIXED_MARKET_PACK_KEYS,
) -> dict[str, Any]:
    combinations: dict[tuple[str, str], dict[str, Any]] = {}
    for symbol, timeframe in market_keys:
        frame = market_pack[(symbol, timeframe)].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        strategy = _build_strategy(frame, symbol=symbol, timeframe=timeframe, strategy_module=strategy_module)
        split_frames = _split_frame(frame, timeframe=timeframe)
        regime = classify_ema200_regime(frame["close"])
        combination_result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "splits": {},
            "regime_slices": {},
            "params": dict(strategy.params),
            "diagnostics": strategy.diagnostics,
        }

        out_of_sample_bundle: dict[str, Any] | None = None
        for split_name, split_frame in split_frames.items():
            split_mask = frame["timestamp"].isin(split_frame["timestamp"])
            portfolio = _run_portfolio(
                split_frame,
                long_entries=strategy.long_entries.loc[split_mask].reset_index(drop=True),
                long_exits=strategy.long_exits.loc[split_mask].reset_index(drop=True),
                short_entries=strategy.short_entries.loc[split_mask].reset_index(drop=True),
                short_exits=strategy.short_exits.loc[split_mask].reset_index(drop=True),
            )
            trades = portfolio.trades.records.copy()
            equity_curve = portfolio.value()
            position_mask = portfolio.position_mask()
            metrics = compute_metrics(
                equity_curve=equity_curve,
                trades=trades,
                position_mask=position_mask,
                annualization=annualization_factor(symbol, timeframe),
                initial_cash=INITIAL_CASH,
            )
            combination_result["splits"][split_name] = metrics
            if split_name == "out_of_sample":
                out_of_sample_bundle = {
                    "frame": split_frame.reset_index(drop=True),
                    "equity_curve": equity_curve.reset_index(drop=True),
                    "trades": trades.reset_index(drop=True),
                    "position_mask": position_mask.reset_index(drop=True),
                    "regime": regime.loc[split_mask].reset_index(drop=True),
                }

        if out_of_sample_bundle is None:
            raise ValueError("out_of_sample split is required")
        combination_result["regime_slices"] = _build_regime_slices(
            out_of_sample_bundle,
            symbol=symbol,
            timeframe=timeframe,
        )
        combinations[(symbol, timeframe)] = combination_result

    return {
        "combinations": combinations,
        "aggregate": {
            "split_means": {
                "in_sample": aggregate_metric_means(combinations, split_name="in_sample"),
                "validation": aggregate_metric_means(combinations, split_name="validation"),
                "out_of_sample": aggregate_metric_means(combinations, split_name="out_of_sample"),
            },
            "out_of_sample_sharpe_values": [
                float(combination["splits"]["out_of_sample"]["sharpe"])
                for combination in combinations.values()
            ],
        },
    }


def _build_strategy(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    strategy_module: object,
):
    build_strategy = getattr(strategy_module, "build_strategy", None)
    if build_strategy is None:
        raise ValueError("strategy module must expose build_strategy")
    context = StrategyContext(
        open=frame["open"],
        high=frame["high"],
        low=frame["low"],
        close=frame["close"],
        volume=frame["volume"],
        symbol=symbol,
        timeframe=timeframe,
        indicators=DEFAULT_INDICATORS,
        regimes=DEFAULT_REGIMES,
    )
    return build_strategy(context)


def _split_frame(frame: pd.DataFrame, *, timeframe: str) -> dict[str, pd.DataFrame]:
    latest_timestamp = frame["timestamp"].max()
    windows = SPLIT_WINDOWS[timeframe]
    out_start = latest_timestamp - pd.Timedelta(days=windows["out_of_sample"])
    validation_start = out_start - pd.Timedelta(days=windows["validation"])
    in_sample_start = validation_start - pd.Timedelta(days=windows["in_sample"])
    return {
        "in_sample": frame.loc[
            (frame["timestamp"] > in_sample_start) & (frame["timestamp"] <= validation_start)
        ].reset_index(drop=True),
        "validation": frame.loc[
            (frame["timestamp"] > validation_start) & (frame["timestamp"] <= out_start)
        ].reset_index(drop=True),
        "out_of_sample": frame.loc[frame["timestamp"] > out_start].reset_index(drop=True),
    }


def _run_portfolio(
    split_frame: pd.DataFrame,
    *,
    long_entries: pd.Series,
    long_exits: pd.Series,
    short_entries: pd.Series,
    short_exits: pd.Series,
):
    return vbt.Portfolio.from_signals(
        close=split_frame["close"],
        entries=long_entries.astype(bool),
        exits=long_exits.astype(bool),
        short_entries=short_entries.astype(bool),
        short_exits=short_exits.astype(bool),
        init_cash=INITIAL_CASH,
        fees=FEES_PER_SIDE,
        slippage=SLIPPAGE_PER_SIDE,
        accumulate=False,
        upon_opposite_entry="Close",
    )


def _build_regime_slices(
    out_of_sample_bundle: Mapping[str, Any],
    *,
    symbol: str,
    timeframe: str,
) -> dict[str, dict[str, Any]]:
    regime_slices: dict[str, dict[str, Any]] = {}
    annualization = annualization_factor(symbol, timeframe)
    regime = out_of_sample_bundle["regime"]
    for label in ("bull", "bear"):
        bar_mask = regime.eq(label)
        bar_count = int(bar_mask.sum())
        window_exists = regime_window_exists(bar_count)
        if not window_exists:
            metrics = {metric: 0.0 for metric in METRIC_NAMES}
            metrics["trade_count"] = 0
        else:
            frame = out_of_sample_bundle["frame"].loc[bar_mask].reset_index(drop=True)
            equity_curve = out_of_sample_bundle["equity_curve"].loc[bar_mask].reset_index(drop=True)
            position_mask = out_of_sample_bundle["position_mask"].loc[bar_mask].reset_index(drop=True)
            trades = _slice_trades_for_regime(
                out_of_sample_bundle["trades"],
                bar_mask.reset_index(drop=True),
            )
            metrics = compute_metrics(
                equity_curve=equity_curve,
                trades=trades,
                position_mask=position_mask,
                annualization=annualization,
                initial_cash=INITIAL_CASH,
            )
        regime_slices[label] = {
            "window_exists": window_exists,
            "bar_count": bar_count,
            "metrics": metrics,
        }
    return regime_slices


def _slice_trades_for_regime(trades: pd.DataFrame, bar_mask: pd.Series) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    included_indices = set(bar_mask[bar_mask].index.tolist())
    return trades.loc[trades["entry_idx"].isin(included_indices)].reset_index(drop=True)
