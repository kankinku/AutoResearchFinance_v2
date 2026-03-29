from __future__ import annotations

from tests.backtest.test_evaluator import make_backtest_results


def test_prescreener_rejects_zero_exposure_candidate() -> None:
    from finance_autoresearch.backtest.prescreener import prescreen_candidate

    raw_results = make_backtest_results([0.6, 0.5, 0.4, 0.3, 0.2, 0.1])
    for combination in raw_results["combinations"].values():
        combination["splits"]["out_of_sample"]["exposure"] = 0.0

    result = prescreen_candidate(
        candidate_id="candidate-001",
        backtest_results=raw_results,
    )

    assert result.passed is False
    assert result.reason == "zero_exposure"


def test_prescreener_rejects_overtrading_candidate() -> None:
    from finance_autoresearch.backtest.prescreener import prescreen_candidate

    raw_results = make_backtest_results([0.6, 0.5, 0.4, 0.3, 0.2, 0.1])
    for combination in raw_results["combinations"].values():
        combination["splits"]["out_of_sample"]["turnover"] = 45.0
        combination["splits"]["out_of_sample"]["trade_count"] = 180

    result = prescreen_candidate(
        candidate_id="candidate-002",
        backtest_results=raw_results,
    )

    assert result.passed is False
    assert result.reason == "extreme_overtrading"


def test_prescreener_rejects_single_bad_combination_even_if_mean_looks_fine() -> None:
    from finance_autoresearch.backtest.prescreener import prescreen_candidate

    raw_results = make_backtest_results([0.6, 0.5, 0.4, 0.3, 0.2, 0.1])
    raw_results["combinations"][("QQQ", "1d")]["splits"]["out_of_sample"]["exposure"] = 0.0

    result = prescreen_candidate(
        candidate_id="candidate-003",
        backtest_results=raw_results,
    )

    assert result.passed is False
    assert result.reason == "zero_exposure"
    assert result.metrics["failed_combination"] == "QQQ 1d"
