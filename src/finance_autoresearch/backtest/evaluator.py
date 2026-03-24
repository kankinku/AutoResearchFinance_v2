from __future__ import annotations

import math
from typing import Any

import numpy as np

from finance_autoresearch.backtest.scoring import METRIC_NAMES, even_median


def evaluate_backtest_results(results: dict[str, Any]) -> dict[str, Any]:
    combinations: dict[tuple[str, str], dict[str, Any]] = dict(results["combinations"])
    out_of_sample_sharpes = [
        float(combination["splits"]["out_of_sample"]["sharpe"])
        for combination in combinations.values()
    ]
    guardrail_failures = _guardrail_failures(combinations)
    aggregate = {
        "mean_out_of_sample_total_return": float(
            np.mean(
                [
                    combination["splits"]["out_of_sample"]["total_return"]
                    for combination in combinations.values()
                ]
            )
        ),
        "worst_out_of_sample_max_drawdown": float(
            max(
                combination["splits"]["out_of_sample"]["max_drawdown"]
                for combination in combinations.values()
            )
        ),
        "mean_out_of_sample_turnover": float(
            np.mean(
                [
                    combination["splits"]["out_of_sample"]["turnover"]
                    for combination in combinations.values()
                ]
            )
        ),
    }
    return {
        "score": even_median(out_of_sample_sharpes),
        "metrics": {
            "combinations": combinations,
            "aggregate": aggregate,
        },
        "guardrails_passed": len(guardrail_failures) == 0,
        "guardrail_failures": guardrail_failures,
    }


def _guardrail_failures(
    combinations: dict[tuple[str, str], dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    required_metrics = {
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
    }
    valid_trade_count = 0
    turnovers: list[float] = []
    symbol_exposure: dict[str, bool] = {}
    bull_exposure: dict[str, bool] = {}
    bear_exposure: dict[str, bool] = {}
    bull_window_exists: dict[str, bool] = {}
    bear_window_exists: dict[str, bool] = {}

    for (symbol, timeframe), combination in combinations.items():
        metrics = combination["splits"]["out_of_sample"]
        for metric_name in required_metrics:
            value = float(metrics[metric_name])
            if not math.isfinite(value):
                failures.append(
                    f"{symbol} {timeframe} must produce finite out_of_sample_{metric_name}"
                )
        if int(metrics["trade_count"]) >= 20:
            valid_trade_count += 1
        if float(metrics["max_drawdown"]) > 0.35:
            failures.append(f"{symbol} {timeframe} out_of_sample_max_drawdown exceeds 0.35")
        turnovers.append(float(metrics["turnover"]))
        symbol_exposure[symbol] = symbol_exposure.get(symbol, False) or float(metrics["exposure"]) > 0.0

        bull_slice = combination["regime_slices"]["bull"]
        bear_slice = combination["regime_slices"]["bear"]
        bull_window_exists[symbol] = bull_window_exists.get(symbol, False) or bool(
            bull_slice["window_exists"]
        )
        bear_window_exists[symbol] = bear_window_exists.get(symbol, False) or bool(
            bear_slice["window_exists"]
        )
        bull_exposure[symbol] = bull_exposure.get(symbol, False) or float(
            bull_slice["metrics"]["exposure"]
        ) > 0.0
        bear_exposure[symbol] = bear_exposure.get(symbol, False) or float(
            bear_slice["metrics"]["exposure"]
        ) > 0.0

    if valid_trade_count < 4:
        failures.append("at least four combinations must have out_of_sample_trade_count >= 20")
    if turnovers and float(np.mean(turnovers)) > 12.0:
        failures.append("mean out_of_sample_turnover must be <= 12.0")
    for symbol in ("QQQ", "IWM", "BTC-USD"):
        if not symbol_exposure.get(symbol, False):
            failures.append(f"{symbol} must have non-zero out_of_sample exposure")
        if bull_window_exists.get(symbol, False) and not bull_exposure.get(symbol, False):
            failures.append(f"{symbol} must show non-zero bull exposure when a bull window exists")
        if bear_window_exists.get(symbol, False) and not bear_exposure.get(symbol, False):
            failures.append(f"{symbol} must show non-zero bear exposure when a bear window exists")
    return failures
