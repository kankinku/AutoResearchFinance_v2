from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.backtest.p2_policy import (
    ATRVolatilitySizing,
    P2ResearchPolicy,
    RegimeRoute,
)
from core.data.contracts import Bar, MarketDataSet
from strategy_ir.schema import StrategyIR


def _ir(atr=False):
    indicators = {"m": {"type": "SMA", "period": 1}}
    if atr:
        indicators["a"] = {"type": "ATR", "period": 1}
    return StrategyIR.model_validate(
        dict(
            schema_version=1,
            id="p2",
            family="test",
            generation=0,
            indicators=indicators,
            entry={
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
            },
            exit={"logic": "AND", "conditions": [{"op": "less_than", "left": "close", "value": 0}]},
            risk={"stop_loss_pct": 0, "take_profit_pct": 0, "position_size_pct": 100},
        )
    )


def _data(quotes):
    return MarketDataSet(
        "p2-unit",
        "development",
        tuple(
            Bar(datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i), "QQQ", *quote, 1000)
            for i, quote in enumerate(quotes)
        ),
    )


def test_regime_position_uses_completed_signal_bar():
    data = _data([(100, 100, 100, 100), (120, 120, 120, 120), (120, 120, 120, 120)])
    ir = _ir()
    before = BacktestEngine().run(BacktestRequest("old", "x", data, 1000, ir))
    route = RegimeRoute(
        name="low",
        when={"logic": "AND", "conditions": [{"op": "less_than", "left": "close", "value": 110}]},
        entry={"logic": "AND", "conditions": [{"op": "greater_than", "left": "close", "value": 1}]},
        position_size_pct=20,
    )
    policy = P2ResearchPolicy(regimes=(route,))
    result = BacktestEngine().run(BacktestRequest("new", "x", data, 1000, ir, p2_policy=policy))
    assert before.trades[0].notional == pytest.approx(1000)
    assert result.trades[0].notional == pytest.approx(200)
    assert result.trades[0].price == 120
    assert result.strategy_hash != before.strategy_hash


def test_atr_uses_signal_close_not_future_open():
    data = _data([(100, 105, 95, 100), (130, 135, 125, 130), (130, 135, 125, 130)])
    policy = P2ResearchPolicy(
        atr_sizing=ATRVolatilitySizing(
            atr_alias="a", target_atr_pct=1, min_position_size_pct=5, max_position_size_pct=90
        )
    )
    result = BacktestEngine().run(
        BacktestRequest("p2atr", "x", data, 1000, _ir(atr=True), p2_policy=policy)
    )
    assert result.trades[0].notional == pytest.approx(100)
    assert result.trades[0].price == 130


def test_risk_metrics_gate_is_explicit_and_fail_closed():
    from core.backtest.p2_policy import ChildRiskBudget, assess_child_risk_metrics

    cap = ChildRiskBudget(max_child_mdd_pct=30, max_mdd_increase_pp=5, min_closed_trades=30)
    accepted = assess_child_risk_metrics(
        parent_mdd_pct=20, child_mdd_pct=24, child_closed_trades=36, budget=cap
    )
    over = assess_child_risk_metrics(
        parent_mdd_pct=20, child_mdd_pct=28, child_closed_trades=36, budget=cap
    )
    low_trades = assess_child_risk_metrics(
        parent_mdd_pct=20, child_mdd_pct=24, child_closed_trades=8, budget=cap
    )
    assert accepted["eligible"] is True
    assert over["eligible"] is False
    assert low_trades["eligible"] is False
    with pytest.raises(ValueError, match="finite"):
        assess_child_risk_metrics(
            parent_mdd_pct=float("nan"), child_mdd_pct=24, child_closed_trades=36, budget=cap
        )


def test_fail_closed_if_no_regime_and_unrecognized_atr():
    data = _data([(100, 100, 100, 100)] * 4)
    ir = _ir()
    policy = P2ResearchPolicy(
        regimes=(
            RegimeRoute(
                name="bear",
                when={
                    "logic": "AND",
                    "conditions": [{"op": "less_than", "left": "close", "value": 20}],
                },
                entry={
                    "logic": "AND",
                    "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
                },
                position_size_pct=25,
            ),
        )
    )
    result = BacktestEngine().run(BacktestRequest("none", "x", data, 1000, ir, p2_policy=policy))
    assert not result.trades
    bad = P2ResearchPolicy(
        atr_sizing=ATRVolatilitySizing(
            atr_alias="undefined",
            target_atr_pct=1,
            min_position_size_pct=5,
            max_position_size_pct=90,
        )
    )
    with pytest.raises(ValueError, match="ATR"):
        BacktestEngine().run(BacktestRequest("bad", "x", data, 1000, ir, p2_policy=bad))


def test_p2_policy_rejects_multisymbol_unaudited_execution():
    data = _data([(100, 100, 100, 100)] * 4)
    second = tuple(
        type(b)(b.timestamp, "SPY", b.open, b.high, b.low, b.close, b.volume) for b in data.bars
    )
    multi = MarketDataSet("p2-multi", "development", data.bars + second)
    route = RegimeRoute(
        name="on",
        when={"logic": "AND", "conditions": [{"op": "greater_than", "left": "close", "value": 0}]},
        entry={"logic": "AND", "conditions": [{"op": "greater_than", "left": "close", "value": 0}]},
    )
    policy = P2ResearchPolicy(regimes=(route,))
    with pytest.raises(ValueError, match="single symbol"):
        BacktestEngine().run(BacktestRequest("multi", "x", multi, 1000, _ir(), p2_policy=policy))


def test_policy_requires_strategy_and_rejects_unusable_conditions():
    data = _data([(100, 100, 100, 100)] * 4)
    route = RegimeRoute(
        name="impossible",
        when={"logic": "AND", "conditions": [{"op": "greater_than", "left": "close", "value": 50}]},
        entry={"logic": "AND", "conditions": [{"op": "cross_above", "left": "close"}]},
    )
    policy = P2ResearchPolicy(regimes=(route,))
    with pytest.raises(ValueError, match="cross requires"):
        BacktestEngine().run(BacktestRequest("badroute", "x", data, 1000, _ir(), p2_policy=policy))
    with pytest.raises(ValueError, match="requires an explicit"):
        BacktestEngine().run(BacktestRequest("no_strategy", "x", data, 1000, p2_policy=policy))
