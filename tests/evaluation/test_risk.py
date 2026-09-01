from __future__ import annotations

import pytest

from evaluation.risk import evaluate_risk_policy
from strategy_ir.schema import RiskConfig


def test_risk_evaluation_records_daily_loss_and_policy_compliance() -> None:
    evaluation = evaluate_risk_policy(
        (100.0, 98.0, 99.0, 95.0),
        RiskConfig(
            stop_loss_pct=0,
            take_profit_pct=0,
            risk_appetite=0.4,
            daily_loss_limit_pct=2.0,
            daily_loss_action="stop",
        ),
    )

    assert evaluation.risk_appetite == pytest.approx(0.4)
    assert evaluation.max_daily_loss_pct == pytest.approx(4.04, abs=0.01)
    assert evaluation.daily_loss_breaches == 1
    assert evaluation.compliant is False
    assert evaluation.action == "stop"


def test_risk_evaluation_without_limit_is_observational() -> None:
    evaluation = evaluate_risk_policy(
        (100.0, 90.0),
        RiskConfig(stop_loss_pct=0, take_profit_pct=0),
    )

    assert evaluation.daily_loss_breaches == 0
    assert evaluation.compliant is True
