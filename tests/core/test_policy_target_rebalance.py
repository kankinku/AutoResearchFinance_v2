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
    assert result.trades[0].notional == pytest.approx(249.93748437109278)
    assert all(
        trade.policy_id == "policy" and trade.reason_hash == "a" * 64 and len(trade.fill_id) == 64
        for trade in result.trades
    )
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


def test_net_of_fee_weights_and_deterministic_fill_ids():
    data, decisions = fixture()
    cost = CostModel("costed", 10, 10, SlippageModel(10))
    result = BacktestEngine().run(
        BacktestRequest("test", "program", data, 1000, cost_model=cost, policy_decisions=decisions)
    )
    units = 0.0
    cash = 1000.0
    for trade, target in zip(result.trades, (0.25, 0.65, 0), strict=True):
        if trade.side == "buy":
            units += trade.quantity
            cash -= trade.quantity * trade.price + trade.cost
        else:
            units -= trade.quantity
            cash += trade.notional - trade.cost
        equity = cash + units * trade.price
        assert units * trade.price / equity == pytest.approx(target, abs=1e-10)
    assert len({trade.fill_id for trade in result.trades}) == 3


def test_legacy_trades_do_not_gain_policy_metadata():
    from tests.core.test_backtest_golden_baseline import _fixture

    strategy, dataset = _fixture()
    result = BacktestEngine().run(
        BacktestRequest("legacy", "legacy", dataset, 1000, strategy=strategy)
    )
    assert all(
        trade.policy_id == trade.reason_hash == trade.fill_id == "" for trade in result.trades
    )
