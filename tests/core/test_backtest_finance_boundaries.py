"""Independently reconciled transaction-cost and cash-ledger boundaries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import inf, nan

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import Bar, MarketDataSet
from strategy_ir.schema import StrategyIR


def fixture(*symbols: str) -> tuple[StrategyIR, MarketDataSet]:
    strategy = StrategyIR.model_validate({
        "schema_version": 1,
        "id": "accounting-boundary",
        "family": "audit",
        "generation": 0,
        "indicators": {"fast": {"type": "SMA", "period": 1}},
        "entry": {
            "logic": "AND",
            "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
        },
        "exit": {"logic": "OR", "conditions": []},
        "risk": {
            "stop_loss_pct": 0,
            "take_profit_pct": 0,
            "position_size_pct": 100,
        },
    })
    bars = tuple(
        Bar(
            datetime(2024, 1, 2, tzinfo=timezone.utc) + timedelta(days=day),
            symbol, 100.0, 100.0, 100.0, 100.0, 1000.0
        )
        for symbol in symbols
        for day in range(3)
    )
    return strategy, MarketDataSet("accounting-v1", "development", bars)


@pytest.mark.parametrize("symbols", [("AAA",), ("AAA", "BBB")])
def test_unaffordable_buy_cost_never_burns_cash_or_creates_zero_unit_trade(
    symbols: tuple[str, ...]
) -> None:
    strategy, data = fixture(*symbols)
    # 110% buy commission: a trade cannot acquire units for the intended budget.
    cost = CostModel("cost-v1", 11_000, 0, SlippageModel(0))
    result = BacktestEngine().run(
        BacktestRequest("bad-cost", "ignored", data, 1000, strategy, cost)
    )
    assert result.trades == ()
    assert result.equity_curve == (1000.0, 1000.0, 1000.0)


@pytest.mark.parametrize("invalid", [nan, inf, -inf])
def test_nonfinite_initial_cash_is_denied_before_backtest(invalid: float) -> None:
    strategy, data = fixture("AAA")
    with pytest.raises(ValueError, match="finite"):
        BacktestEngine().run(
            BacktestRequest("invalid-cash", "hash", data, invalid, strategy)
        )


@pytest.mark.parametrize("invalid", [nan, inf, -inf])
def test_nonfinite_stress_multiplier_is_denied_before_backtest(invalid: float) -> None:
    strategy, data = fixture("AAA")
    with pytest.raises(ValueError, match="finite"):
        BacktestEngine().run(
            BacktestRequest(
                "invalid-stress", "hash", data, 1000, strategy,
                CostModel("cost-v1", 1, 2, SlippageModel(3)),
                cost_stress_multiplier=invalid,
            )
        )


@pytest.mark.parametrize("symbols", [("AAA",), ("AAA", "BBB")])
def test_purchase_cost_reconciles_to_marked_equity_for_flat_prices(
    symbols: tuple[str, ...]
) -> None:
    strategy, data = fixture(*symbols)
    # Manual result: 1000 initial - (10bps commission+spread+slippage)
    # = 999 on the buy open; constant close prices thereafter.
    cost = CostModel("cost-v1", 10, 0, SlippageModel(0))
    result = BacktestEngine().run(
        BacktestRequest("manual-cash", "hash", data, 1000, strategy, cost)
    )
    assert len(result.trades) == len(symbols)
    assert result.equity_curve == pytest.approx((1000.0, 999.0, 999.0))
    assert sum(t.notional + t.cost for t in result.trades) == pytest.approx(1000)
    assert all(t.quantity > 0 and t.cost >= 0 for t in result.trades)
