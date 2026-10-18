from datetime import datetime, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import Bar, MarketDataSet
from strategy_ir.policy_decision import PolicyDecision


def fixture():
    dates = [datetime(2024, 1, n, tzinfo=timezone.utc) for n in range(1, 5)]
    bars = tuple(
        Bar(t, "QQQ", p, p, p, p, 1000) for t, p in zip(dates, (10, 20, 20, 20), strict=True)
    )
    data = MarketDataSet("test-policy-v1", "development", bars)
    decisions = tuple(
        PolicyDecision(dates[i], dates[i + 1], "QQQ", weight, "policy", "a" * 64)
        for i, weight in enumerate((0.25, 0.65, 0))
    )
    return data, decisions


def test_target_weight_next_open_and_cost_accounting():
    data, decisions = fixture()
    cost = CostModel("fixed", 10, 0, SlippageModel(0))
    result = BacktestEngine().run(
        BacktestRequest("test", "program", data, 1000, cost_model=cost, policy_decisions=decisions)
    )
    assert [(t.side, t.timestamp, t.price) for t in result.trades] == [
        ("buy", data.bars[1].timestamp.isoformat(), 20),
        ("buy", data.bars[2].timestamp.isoformat(), 20),
        ("sell", data.bars[3].timestamp.isoformat(), 20),
    ]
    assert result.trades[0].notional == pytest.approx(249.75)
    assert result.trades[1].notional > 390
    assert result.equity_curve[-1] < 1000
    assert result.equity_curve[-1] > 997
    assert (
        BacktestEngine().run(
            BacktestRequest(
                "test", "program", data, 1000, cost_model=cost, policy_decisions=decisions
            )
        )
        == result
    )


def test_rejects_future_or_unscheduled_decision():
    data, decisions = fixture()
    bad = PolicyDecision(
        data.bars[0].timestamp, data.bars[2].timestamp, "QQQ", 0.5, "policy", "a" * 64
    )
    with pytest.raises(ValueError, match="exact next"):
        BacktestEngine().run(BacktestRequest("test", "p", data, 1000, policy_decisions=(bad,)))
    with pytest.raises(ValueError, match="multiple"):
        BacktestEngine().run(
            BacktestRequest("test", "p", data, 1000, policy_decisions=(decisions[0], decisions[0]))
        )
    with pytest.raises(ValueError, match="development"):
        sealed = MarketDataSet("test-policy-v1", "sealed_oos", data.bars)
        BacktestEngine().run(BacktestRequest("test", "p", sealed, 1000, policy_decisions=decisions))
