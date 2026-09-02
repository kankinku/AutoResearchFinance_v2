from __future__ import annotations

from evaluation.benchmark import compare_benchmarks
from evaluation.metrics import calculate_metrics
from evaluation.risk import RiskEvaluation
from evaluation.robustness import RobustnessReport
from evaluation.selector import FunnelConfig, FunnelInput, select_candidate


def _metrics(trades: int = 3):
    return calculate_metrics(
        (100.0, 102.0, 101.0, 110.0),
        tuple(1.0 for _ in range(trades)),
        periods_per_year=3,
    )


def test_funnel_records_all_gates_and_admits_survivor() -> None:
    result = select_candidate(
        FunnelInput(
            "cand-1",
            "trend",
            _metrics(),
            _metrics(),
            RobustnessReport("OK", 0.9, 0.8, 0.7, 0.1, 0.75),
            validation_passed=True,
            parameters={"indicators.fast.period": 5},
            dataset_hash="data-hash",
        ),
        FunnelConfig(
            min_fast_trades=2,
            min_full_trades=2,
            min_full_return=0.0,
            min_robust_score=0.5,
        ),
    )

    assert result.status == "SURVIVOR"
    assert [gate.name for gate in result.gates] == [
        "fast",
        "full",
        "robustness",
        "validation",
        "risk",
        "qqq_cagr_delta",
        "promotion",
    ]
    assert all(gate.passed for gate in result.gates)
    assert result.full_total_return == _metrics().total_return
    assert result.full_max_drawdown == _metrics().max_drawdown
    assert result.full_cagr == _metrics().cagr
    assert result.full_trade_count == _metrics().trade_count
    assert dict(result.parameters or {}) == {"indicators.fast.period": 5}
    assert result.dataset_hash == "data-hash"


def test_funnel_exposes_rejection_reason_and_near_miss() -> None:
    result = select_candidate(
        FunnelInput(
            "cand-2",
            "mean-reversion",
            _metrics(trades=1),
            _metrics(),
            RobustnessReport("OK", 0.9, 0.8, 0.7, 0.1, 0.75),
            validation_passed=True,
        ),
        FunnelConfig(
            min_fast_trades=2,
            min_full_trades=2,
            min_full_return=0.0,
            min_robust_score=0.5,
        ),
    )

    assert result.status == "NEAR_MISS"
    assert result.gates[0].passed is False
    assert result.gates[0].reason == "trade_count"


def test_funnel_preserves_benchmark_comparison_as_an_additional_evaluation() -> None:
    benchmark = compare_benchmarks(
        (100.0, 110.0, 120.0),
        (100.0, 105.0, 110.0),
        (100.0, 106.0, 112.0),
    )
    result = select_candidate(
        FunnelInput(
            "cand-benchmark",
            "trend",
            _metrics(),
            _metrics(),
            RobustnessReport("OK", 0.9, 0.8, 0.7, 0.1, 0.75),
            validation_passed=True,
            full_benchmark=benchmark,
        ),
        FunnelConfig(min_fast_trades=2, min_full_trades=2, min_robust_score=0.5),
    )

    assert result.full_benchmark is benchmark
    assert result.full_benchmark.qqq_excess_return > 0


def test_funnel_rejects_candidate_that_breaches_declared_daily_loss_policy() -> None:
    risk = RiskEvaluation(None, 2.0, 1.0, "stop", 2.0, 1, False)
    result = select_candidate(
        FunnelInput(
            "cand-risk",
            "trend",
            _metrics(),
            _metrics(),
            RobustnessReport("OK", 0.9, 0.8, 0.7, 0.1, 0.75),
            validation_passed=True,
            risk_evaluation=risk,
        ),
        FunnelConfig(min_fast_trades=2, min_full_trades=2, min_robust_score=0.5),
    )

    risk_gate = next(gate for gate in result.gates if gate.name == "risk")
    assert risk_gate.passed is False
    assert result.status == "REJECT"


def test_funnel_applies_qqq_annualized_excess_target_when_configured() -> None:
    strategy_equity = (100.0,) + (110.0,) * 251 + (120.0,)
    qqq_prices = (100.0,) + (105.0,) * 251 + (110.0,)
    nasdaq_prices = (100.0,) + (106.0,) * 251 + (112.0,)
    benchmark = compare_benchmarks(
        strategy_equity,
        qqq_prices,
        nasdaq_prices,
    )
    result = select_candidate(
        FunnelInput(
            "cand-qqq-target",
            "trend",
            _metrics(),
            _metrics(),
            RobustnessReport("OK", 0.9, 0.8, 0.7, 0.1, 0.75),
            validation_passed=True,
            full_benchmark=benchmark,
        ),
        FunnelConfig(
            min_fast_trades=2,
            min_full_trades=2,
            min_robust_score=0.5,
            min_qqq_cagr_delta=0.10,
        ),
    )

    qqq_gate = next(gate for gate in result.gates if gate.name == "qqq_cagr_delta")
    assert qqq_gate.passed is False
    assert qqq_gate.threshold == 0.10
