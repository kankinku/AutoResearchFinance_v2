from __future__ import annotations

from pathlib import Path

import pytest

from tests.backtest.test_evaluator import make_backtest_results


def write_candidate_strategy(path: Path, *, lines: list[str] | None = None) -> None:
    body = lines or [
        "import pandas as pd",
        "",
        "from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition",
        "",
        "def build_strategy(context: StrategyContext) -> StrategyDefinition:",
        "    regime = context.regimes.classify_ema200_regime(context.close)",
        "    no_signal = context.close > (context.close + 1)",
        "    return StrategyDefinition(",
        "        long_entries=no_signal,",
        "        long_exits=no_signal,",
        "        short_entries=no_signal,",
        "        short_exits=no_signal,",
        "        regime=regime,",
        "        params={'tag': 'candidate'},",
        "        diagnostics={'tag': 'candidate'},",
        "    )",
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")


def make_candidate_evaluation() -> dict[str, object]:
    return {
        "score": 0.55,
        "metrics": {
            "aggregate": {
                "mean_out_of_sample_turnover": 4.0,
                "mean_out_of_sample_total_return": 0.12,
                "worst_out_of_sample_max_drawdown": 0.12,
            },
            "combinations": {},
        },
        "guardrails_passed": True,
        "guardrail_failures": [],
    }


def test_falsifier_flags_validation_instability(tmp_path: Path) -> None:
    from finance_autoresearch.backtest.falsifier import falsify_candidate

    strategy_path = tmp_path / "strategy_candidate.py"
    write_candidate_strategy(strategy_path)
    raw_results = make_backtest_results([0.6, 0.5, 0.4, 0.7, 0.3, 0.2])
    for combination in raw_results["combinations"].values():
        combination["splits"]["validation"]["sharpe"] = 2.1
        combination["splits"]["out_of_sample"]["sharpe"] = -0.2

    report = falsify_candidate(
        backtest_results=raw_results,
        evaluation=make_candidate_evaluation(),
        strategy_path=strategy_path,
    )

    assert report.passed is False
    assert report.checks["validation_stability"]["passed"] is False


def test_falsifier_flags_single_bad_combination_even_when_mean_gap_is_small(
    tmp_path: Path,
) -> None:
    from finance_autoresearch.backtest.falsifier import falsify_candidate

    strategy_path = tmp_path / "strategy_candidate.py"
    write_candidate_strategy(strategy_path)
    raw_results = make_backtest_results([0.6, 0.5, 0.4, 0.7, 0.3, 0.2])
    for combination in raw_results["combinations"].values():
        combination["splits"]["validation"]["sharpe"] = 0.4
        combination["splits"]["out_of_sample"]["sharpe"] = 0.4
    raw_results["combinations"][("QQQ", "1d")]["splits"]["validation"]["sharpe"] = 1.6
    raw_results["combinations"][("QQQ", "1d")]["splits"]["out_of_sample"]["sharpe"] = 0.4

    report = falsify_candidate(
        backtest_results=raw_results,
        evaluation=make_candidate_evaluation(),
        strategy_path=strategy_path,
    )

    assert report.passed is False
    assert report.checks["validation_stability"]["passed"] is False
    assert report.checks["validation_stability"]["mean_gap"] < 1.0
    assert report.checks["validation_stability"]["failed_pairs"] == ["QQQ 1d"]


def test_falsifier_flags_startup_instability(tmp_path: Path) -> None:
    from finance_autoresearch.backtest.falsifier import falsify_candidate

    strategy_path = tmp_path / "strategy_candidate.py"
    write_candidate_strategy(strategy_path)
    raw_results = make_backtest_results([0.6, 0.5, 0.4, 0.7, 0.3, 0.2])
    for combination in raw_results["combinations"].values():
        combination["splits"]["validation"]["trade_count"] = 120
        combination["splits"]["out_of_sample"]["trade_count"] = 5
        combination["splits"]["validation"]["exposure"] = 0.85
        combination["splits"]["out_of_sample"]["exposure"] = 0.05

    report = falsify_candidate(
        backtest_results=raw_results,
        evaluation=make_candidate_evaluation(),
        strategy_path=strategy_path,
    )

    assert report.passed is False
    assert report.checks["startup_stability"]["passed"] is False


def test_falsifier_flags_complexity_overrun(tmp_path: Path) -> None:
    from finance_autoresearch.backtest.falsifier import falsify_candidate

    strategy_path = tmp_path / "strategy_candidate.py"
    write_candidate_strategy(
        strategy_path,
        lines=[
            "import pandas as pd",
            "",
            "from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition",
            "",
            "def build_strategy(context: StrategyContext) -> StrategyDefinition:",
            "    regime = context.regimes.classify_ema200_regime(context.close)",
            "    fast_1 = context.indicators.ema(context.close, 5)",
            "    fast_2 = context.indicators.ema(context.close, 10)",
            "    fast_3 = context.indicators.ema(context.close, 15)",
            "    fast_4 = context.indicators.ema(context.close, 20)",
            "    fast_5 = context.indicators.ema(context.close, 25)",
            "    no_signal = context.close > (context.close + 1)",
            "    return StrategyDefinition(",
            "        long_entries=no_signal,",
            "        long_exits=no_signal,",
            "        short_entries=no_signal,",
            "        short_exits=no_signal,",
            "        regime=regime,",
            "        params={'tag': 'candidate'},",
            "        diagnostics={'tag': 'candidate', 'fast_1': fast_1, 'fast_2': fast_2, 'fast_3': fast_3, 'fast_4': fast_4, 'fast_5': fast_5},",
            "    )",
            "",
        ],
    )

    report = falsify_candidate(
        backtest_results=make_backtest_results([0.6, 0.5, 0.4, 0.7, 0.3, 0.2]),
        evaluation=make_candidate_evaluation(),
        strategy_path=strategy_path,
    )

    assert report.passed is False
    assert report.checks["complexity_budget"]["passed"] is False
