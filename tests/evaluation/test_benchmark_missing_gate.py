from evaluation.metrics import calculate_metrics
from evaluation.robustness import RobustnessReport
from evaluation.selector import FunnelConfig, FunnelInput, select_candidate


def test_missing_qqq_benchmark_is_unmeasured_not_measured_underperformance() -> None:
    metrics = calculate_metrics((100.0, 102.0, 101.0, 110.0), (1.0, 1.0, 1.0), periods_per_year=3)
    candidate = FunnelInput(
        "missing-qqq", "trend", metrics, metrics,
        RobustnessReport("OK", 0.9, 0.8, 0.7, 0.1, 0.75),
        validation_passed=True,
    )
    config = FunnelConfig(
        min_fast_trades=2,
        min_full_trades=2,
        min_robust_score=0.5,
        min_qqq_cagr_delta=0.0,
    )
    result = select_candidate(candidate, config)
    gate = next(g for g in result.gates if g.name == "qqq_cagr_delta")
    assert result.status == "REJECT"
    assert gate.passed is False
    assert gate.threshold == 0.0
    assert gate.actual is None
    assert gate.reason == "benchmark_not_measured"


def test_optional_qqq_benchmark_does_not_falsely_block_selection() -> None:
    metrics = calculate_metrics((100.0, 102.0, 101.0, 110.0), (1.0, 1.0, 1.0), periods_per_year=3)
    candidate = FunnelInput(
        "optional-qqq", "trend", metrics, metrics,
        RobustnessReport("OK", 0.9, 0.8, 0.7, 0.1, 0.75),
        validation_passed=True,
    )
    result = select_candidate(
        candidate, FunnelConfig(min_fast_trades=2, min_full_trades=2, min_robust_score=0.5),
    )
    gate = next(g for g in result.gates if g.name == "qqq_cagr_delta")
    assert result.status == "SURVIVOR"
    assert gate.passed is True
    assert gate.reason is None
