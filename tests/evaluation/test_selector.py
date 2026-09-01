from __future__ import annotations

from evaluation.metrics import calculate_metrics
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
        "promotion",
    ]
    assert all(gate.passed for gate in result.gates)


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
