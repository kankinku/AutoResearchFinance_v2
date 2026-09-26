from __future__ import annotations

from datetime import datetime, timezone

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


def test_intraday_risk_is_aggregated_by_calendar_day() -> None:
    timestamps = (
        datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 14, 45, tzinfo=timezone.utc),
        datetime(2024, 1, 3, 14, 30, tzinfo=timezone.utc),
        datetime(2024, 1, 3, 14, 45, tzinfo=timezone.utc),
    )
    evaluation = evaluate_risk_policy(
        (100.0, 98.5, 100.0, 98.8),
        RiskConfig(
            stop_loss_pct=0,
            take_profit_pct=0,
            daily_loss_limit_pct=1.4,
            daily_loss_action="stop",
        ),
        timestamps=timestamps,
    )

    assert evaluation.max_daily_loss_pct == pytest.approx(1.5)
    assert evaluation.daily_loss_breaches == 1


def test_intraday_risk_does_not_count_each_bar_as_a_new_day() -> None:
    timestamps = (
        datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 14, 45, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc),
    )
    evaluation = evaluate_risk_policy(
        (100.0, 99.0, 99.5),
        RiskConfig(
            stop_loss_pct=0,
            take_profit_pct=0,
            daily_loss_limit_pct=0.75,
            daily_loss_action="stop",
        ),
        timestamps=timestamps,
    )

    assert evaluation.daily_loss_breaches == 1
    assert evaluation.max_daily_loss_pct == pytest.approx(1.0)
