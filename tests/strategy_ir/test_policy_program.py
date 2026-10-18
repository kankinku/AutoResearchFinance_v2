from datetime import datetime, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, MarketDataSet
from strategy_ir.policy_program import PolicySwitch, Predicate, compile_policy_switch


def test_switch_decisions_execute_and_trace():
    bars = tuple(
        Bar(datetime(2024, 1, d, tzinfo=timezone.utc), "QQQ", 20, 20, 20, 20, 1000)
        for d in range(1, 5)
    )
    dataset = MarketDataSet("switch-test", "development", bars)
    program = PolicySwitch((Predicate("signal", "gt", 5),), 0.65, 0.25, "switch")
    decisions = compile_policy_switch(
        dataset, program, {"signal": (1, 10, 2, 3)}, audited_features=frozenset({"signal"})
    )
    assert [d.target_weight for d in decisions] == [0.25, 0.65, 0.25]
    result = BacktestEngine().run(
        BacktestRequest("run", "program", dataset, 1000, policy_decisions=decisions)
    )
    assert [trade.side for trade in result.trades] == ["buy", "buy", "sell"]
    assert all(trade.fill_id and trade.reason_hash for trade in result.trades)


def test_unverified_and_missing_fail_closed():
    bars = tuple(
        Bar(datetime(2024, 1, d, tzinfo=timezone.utc), "QQQ", 20, 20, 20, 20, 1000)
        for d in range(1, 4)
    )
    dataset = MarketDataSet("switch-test", "development", bars)
    program = PolicySwitch((Predicate("signal", "gt", 5),), 0.65, 0.25, "switch")
    with pytest.raises(ValueError, match="not audited"):
        compile_policy_switch(dataset, program, {"signal": (1, 9, 5)}, audited_features=frozenset())
    decisions = compile_policy_switch(
        dataset, program, {"signal": (None, 10, 5)}, audited_features=frozenset({"signal"})
    )
    assert [d.target_weight for d in decisions] == [0, 0.65]
