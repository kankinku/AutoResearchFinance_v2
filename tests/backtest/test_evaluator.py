from __future__ import annotations

import math


def make_split_metrics(
    *,
    sharpe: float,
    total_return: float = 0.12,
    cagr: float = 0.08,
    sortino: float = 1.1,
    max_drawdown: float = 0.12,
    win_rate: float = 0.55,
    profit_factor: float = 1.4,
    turnover: float = 4.0,
    trade_count: int = 30,
    exposure: float = 0.45,
) -> dict[str, float | int]:
    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "turnover": turnover,
        "trade_count": trade_count,
        "exposure": exposure,
    }


def make_regime_slice(
    *,
    window_exists: bool,
    bar_count: int,
    exposure: float,
) -> dict[str, object]:
    return {
        "window_exists": window_exists,
        "bar_count": bar_count,
        "metrics": {
            "total_return": 0.04,
            "cagr": 0.03,
            "sharpe": 0.8,
            "sortino": 1.0,
            "max_drawdown": 0.1,
            "win_rate": 0.5,
            "profit_factor": 1.1,
            "turnover": 3.0,
            "trade_count": 12,
            "exposure": exposure,
        },
    }


def make_backtest_results(sharpes: list[float]) -> dict[str, object]:
    combinations = {}
    keys = [
        ("QQQ", "1d"),
        ("QQQ", "2h"),
        ("IWM", "1d"),
        ("IWM", "2h"),
        ("BTC-USD", "1d"),
        ("BTC-USD", "2h"),
    ]
    for (symbol, timeframe), sharpe in zip(keys, sharpes):
        combinations[(symbol, timeframe)] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "splits": {
                "in_sample": make_split_metrics(sharpe=sharpe + 0.2),
                "validation": make_split_metrics(sharpe=sharpe + 0.1),
                "out_of_sample": make_split_metrics(sharpe=sharpe),
            },
            "regime_slices": {
                "bull": make_regime_slice(window_exists=True, bar_count=80, exposure=0.25),
                "bear": make_regime_slice(window_exists=True, bar_count=70, exposure=0.20),
            },
            "params": {"symbol": symbol, "timeframe": timeframe},
            "diagnostics": {},
        }
    return {"combinations": combinations, "aggregate": {}}


def test_evaluator_uses_even_count_median_for_score() -> None:
    from finance_autoresearch.backtest.evaluator import evaluate_backtest_results

    result = evaluate_backtest_results(make_backtest_results([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]))

    assert result["score"] == 3.5


def test_evaluator_zero_trade_defaults_profit_factor_and_guardrails() -> None:
    from finance_autoresearch.backtest.evaluator import evaluate_backtest_results

    results = make_backtest_results([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    for combination in results["combinations"].values():
        combination["splits"]["out_of_sample"] = make_split_metrics(
            sharpe=0.0,
            total_return=0.0,
            cagr=0.0,
            sortino=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            turnover=0.0,
            trade_count=0,
            exposure=0.0,
        )
        combination["regime_slices"]["bull"] = make_regime_slice(
            window_exists=False,
            bar_count=49,
            exposure=0.0,
        )
        combination["regime_slices"]["bear"] = make_regime_slice(
            window_exists=False,
            bar_count=49,
            exposure=0.0,
        )

    evaluation = evaluate_backtest_results(results)

    assert evaluation["score"] == 0.0
    assert evaluation["metrics"]["combinations"][("QQQ", "1d")]["splits"][
        "out_of_sample"
    ]["profit_factor"] == 0.0
    assert evaluation["guardrails_passed"] is False
    assert any("trade_count" in failure for failure in evaluation["guardrail_failures"])


def test_evaluator_uses_expected_annualization_map() -> None:
    from finance_autoresearch.backtest.scoring import ANNUALIZATION_FACTORS

    assert ANNUALIZATION_FACTORS == {
        ("QQQ", "1d"): 252,
        ("IWM", "1d"): 252,
        ("BTC-USD", "1d"): 365,
        ("QQQ", "2h"): 756,
        ("IWM", "2h"): 756,
        ("BTC-USD", "2h"): 4380,
    }


def test_evaluator_requires_50_bar_regime_window() -> None:
    from finance_autoresearch.backtest.evaluator import evaluate_backtest_results

    results = make_backtest_results([1.0, 1.1, 1.2, 1.3, 1.4, 1.5])
    for key, combination in results["combinations"].items():
        combination["regime_slices"]["bull"] = make_regime_slice(
            window_exists=False,
            bar_count=49,
            exposure=0.0,
        )
        combination["regime_slices"]["bear"] = make_regime_slice(
            window_exists=True,
            bar_count=75,
            exposure=0.3,
        )
        if key[0] == "BTC-USD":
            combination["splits"]["out_of_sample"]["exposure"] = 0.5

    evaluation = evaluate_backtest_results(results)

    assert evaluation["guardrails_passed"] is True
    assert not any("bull exposure" in failure for failure in evaluation["guardrail_failures"])


def test_evaluator_enforces_full_guardrail_set() -> None:
    from finance_autoresearch.backtest.evaluator import evaluate_backtest_results

    results = make_backtest_results([1.0, math.nan, 0.5, 0.2, 0.1, -0.3])
    combinations = results["combinations"]
    combinations[("QQQ", "1d")]["splits"]["out_of_sample"]["trade_count"] = 10
    combinations[("QQQ", "2h")]["splits"]["out_of_sample"]["trade_count"] = 15
    combinations[("IWM", "1d")]["splits"]["out_of_sample"]["trade_count"] = 18
    combinations[("IWM", "2h")]["splits"]["out_of_sample"]["max_drawdown"] = 0.4
    combinations[("BTC-USD", "1d")]["splits"]["out_of_sample"]["turnover"] = 16.0
    combinations[("QQQ", "1d")]["splits"]["out_of_sample"]["turnover"] = 14.0
    combinations[("QQQ", "2h")]["splits"]["out_of_sample"]["turnover"] = 15.0
    combinations[("IWM", "1d")]["splits"]["out_of_sample"]["turnover"] = 13.0
    combinations[("IWM", "2h")]["splits"]["out_of_sample"]["turnover"] = 14.0
    combinations[("BTC-USD", "2h")]["splits"]["out_of_sample"]["turnover"] = 16.0
    combinations[("BTC-USD", "2h")]["splits"]["out_of_sample"]["exposure"] = 0.0
    for combination in combinations.values():
        combination["regime_slices"]["bull"] = make_regime_slice(
            window_exists=True,
            bar_count=80,
            exposure=0.0,
        )
        combination["regime_slices"]["bear"] = make_regime_slice(
            window_exists=True,
            bar_count=80,
            exposure=0.0,
        )

    evaluation = evaluate_backtest_results(results)

    assert evaluation["guardrails_passed"] is False
    assert any("finite" in failure for failure in evaluation["guardrail_failures"])
    assert any("trade_count" in failure for failure in evaluation["guardrail_failures"])
    assert any("max_drawdown" in failure for failure in evaluation["guardrail_failures"])
    assert any("turnover" in failure for failure in evaluation["guardrail_failures"])
    assert any("exposure" in failure for failure in evaluation["guardrail_failures"])


def test_analyzer_returns_structured_summary() -> None:
    from finance_autoresearch.backtest.analyzer import analyze_backtest_results
    from finance_autoresearch.backtest.evaluator import evaluate_backtest_results

    backtest_results = make_backtest_results([1.2, 1.1, 0.9, 0.8, 1.0, 1.3])
    evaluation = evaluate_backtest_results(backtest_results)

    analysis = analyze_backtest_results(backtest_results, evaluation)

    assert set(analysis) == {
        "strengths",
        "weaknesses",
        "coverage_gaps",
        "regime_observations",
        "next_hypothesis_hints",
        "summary",
    }
    assert isinstance(analysis["summary"], str)
    assert analysis["summary"]
