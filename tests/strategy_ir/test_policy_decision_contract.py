from datetime import datetime, timezone

import pytest

from strategy_ir.policy_decision import PolicyDecision


def test_policy_decision_immutable_and_causal() -> None:
    decision = PolicyDecision(
        decided_at=datetime(2025, 3, 3, 21, tzinfo=timezone.utc),
        executable_at=datetime(2025, 3, 4, 14, 30, tzinfo=timezone.utc),
        symbol="QQQ", target_weight=0.25, policy_id="switch/trend",
        reason_hash="a" * 64,
    )
    assert decision.target_weight == 0.25
    assert decision.schema_version == 1
    with pytest.raises(AttributeError):
        decision.target_weight = 0.9  # type: ignore[misc]


@pytest.mark.parametrize("weight", [-0.1, 1.01, float("nan"), float("inf")])
def test_policy_decision_rejects_unsafe_weight(weight: float) -> None:
    with pytest.raises(ValueError):
        _decision(target_weight=weight)


def test_policy_decision_rejects_invalid_time_order_or_timezone() -> None:
    with pytest.raises(ValueError):
        _decision(executable_at=datetime(2025, 3, 2, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        _decision(decided_at=datetime(2025, 3, 3, 21))
    with pytest.raises(ValueError):
        _decision(executable_at=datetime(2025, 3, 3, 21, tzinfo=timezone.utc))


@pytest.mark.parametrize("field,value", [("symbol", ""), ("policy_id", ""), ("reason_hash", "bad")])
def test_policy_decision_rejects_missing_provenance(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        _decision(**{field: value})


def _decision(**overrides: object) -> PolicyDecision:
    values = dict(
        decided_at=datetime(2025, 3, 3, 21, tzinfo=timezone.utc),
        executable_at=datetime(2025, 3, 4, 14, 30, tzinfo=timezone.utc),
        symbol="QQQ", target_weight=1.0, policy_id="policy-1",
        reason_hash="b" * 64,
    )
    values.update(overrides)
    return PolicyDecision(**values)
