from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

ANNUALIZATION_FACTORS: dict[tuple[str, str], int] = {
    ("QQQ", "1d"): 252,
    ("IWM", "1d"): 252,
    ("BTC-USD", "1d"): 365,
    ("QQQ", "2h"): 756,
    ("IWM", "2h"): 756,
    ("BTC-USD", "2h"): 4380,
}
METRIC_NAMES: tuple[str, ...] = (
    "total_return",
    "cagr",
    "sharpe",
    "sortino",
    "max_drawdown",
    "win_rate",
    "profit_factor",
    "turnover",
    "trade_count",
    "exposure",
)


def annualization_factor(symbol: str, timeframe: str) -> int:
    return ANNUALIZATION_FACTORS[(symbol, timeframe)]


def even_median(values: Iterable[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def regime_window_exists(bar_count: int) -> bool:
    return bar_count >= 50


def zero_trade_metrics() -> dict[str, float | int]:
    return {
        "total_return": 0.0,
        "cagr": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "turnover": 0.0,
        "trade_count": 0,
        "exposure": 0.0,
    }


def compute_metrics(
    *,
    equity_curve: pd.Series,
    trades: pd.DataFrame,
    position_mask: pd.Series,
    annualization: int,
    initial_cash: float,
) -> dict[str, float | int]:
    if equity_curve.empty:
        return zero_trade_metrics()

    trade_count = int(len(trades))
    if trade_count == 0:
        metrics = zero_trade_metrics()
        metrics["max_drawdown"] = compute_max_drawdown(equity_curve)
        return metrics

    pnl = pd.Series(trades["pnl"], dtype=float)
    entry_count = trade_count
    exit_count = int((trades["status"] == 1).sum())
    return {
        "total_return": compute_total_return(equity_curve, initial_cash),
        "cagr": compute_cagr(equity_curve, annualization, initial_cash),
        "sharpe": compute_sharpe(equity_curve, annualization),
        "sortino": compute_sortino(equity_curve, annualization),
        "max_drawdown": compute_max_drawdown(equity_curve),
        "win_rate": compute_win_rate(pnl),
        "profit_factor": compute_profit_factor(pnl),
        "turnover": compute_turnover(
            entry_count=entry_count,
            exit_count=exit_count,
            split_bar_count=len(equity_curve),
            annualization=annualization,
        ),
        "trade_count": trade_count,
        "exposure": compute_exposure(position_mask),
    }


def compute_total_return(equity_curve: pd.Series, initial_cash: float) -> float:
    if equity_curve.empty:
        return 0.0
    return float((equity_curve.iloc[-1] / initial_cash) - 1.0)


def compute_cagr(equity_curve: pd.Series, annualization: int, initial_cash: float) -> float:
    if equity_curve.empty:
        return 0.0
    total_bars = len(equity_curve)
    if total_bars <= 0:
        return 0.0
    ending_value = float(equity_curve.iloc[-1])
    if ending_value <= 0.0:
        return -1.0
    return float((ending_value / initial_cash) ** (annualization / total_bars) - 1.0)


def compute_sharpe(equity_curve: pd.Series, annualization: int) -> float:
    bar_returns = equity_curve.pct_change().fillna(0.0)
    std = float(bar_returns.std(ddof=0))
    if std == 0.0:
        return 0.0
    return float(bar_returns.mean() / std * math.sqrt(annualization))


def compute_sortino(equity_curve: pd.Series, annualization: int) -> float:
    bar_returns = equity_curve.pct_change().fillna(0.0)
    downside_returns = bar_returns.clip(upper=0.0)
    downside_std = float(np.sqrt(np.mean(np.square(downside_returns.to_numpy()))))
    if downside_std == 0.0:
        return 0.0
    return float(bar_returns.mean() / downside_std * math.sqrt(annualization))


def compute_max_drawdown(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return 0.0
    running_max = equity_curve.cummax()
    drawdown = (running_max - equity_curve) / running_max.replace(0.0, np.nan)
    return float(drawdown.fillna(0.0).max())


def compute_win_rate(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    return float((pnl > 0.0).mean())


def compute_profit_factor(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    gross_profit = float(pnl[pnl > 0.0].sum())
    gross_loss = float((-pnl[pnl < 0.0]).sum())
    if gross_loss == 0.0:
        return 999.0 if gross_profit > 0.0 else 0.0
    return float(gross_profit / gross_loss)


def compute_turnover(
    *,
    entry_count: int,
    exit_count: int,
    split_bar_count: int,
    annualization: int,
) -> float:
    split_years = split_bar_count / annualization
    denominator = max(split_years, 1 / annualization)
    return float((entry_count + exit_count) / denominator)


def compute_exposure(position_mask: pd.Series) -> float:
    if position_mask.empty:
        return 0.0
    return float(position_mask.astype(bool).mean())


def aggregate_metric_means(
    combinations: dict[tuple[str, str], dict[str, Any]],
    *,
    split_name: str,
) -> dict[str, float]:
    return {
        metric: float(
            np.mean(
                [
                    float(combination["splits"][split_name][metric])
                    for combination in combinations.values()
                ]
            )
        )
        for metric in METRIC_NAMES
    }
