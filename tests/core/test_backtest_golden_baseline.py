"""Frozen, independently hand-calculated behavior before finance-core refactoring.

These assertions lock next-open fills, cash conservation, proportional trading
costs, order chronology and deterministic result hashes. They intentionally use
small synthetic bars so no external market-data provider is required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import Bar, MarketDataSet
from strategy_ir.schema import Condition, StrategyIR


def _fixture() -> tuple[StrategyIR, MarketDataSet]:
    strategy = StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "golden-next-open-v1",
            "family": "fixture",
            "generation": 0,
            "indicators": {"dummy": {"type": "SMA", "period": 1}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
            },
            "exit": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "close", "value": 0}],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )
    bars = tuple(
        Bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=index),
            "GOLDEN",
            opening,
            max(opening, closing),
            min(opening, closing),
            closing,
            1_000,
        )
        for index, (opening, closing) in enumerate(((10, 20), (50, 60), (70, 80)))
    )
    return strategy, MarketDataSet("frozen-fixture-v1", "development", bars)


def test_golden_next_open_cost_and_equity_accounting() -> None:
    strategy, dataset = _fixture()
    cost = CostModel("frozen-cost-v1", 1.0, 2.0, SlippageModel(5.0))
    request = BacktestRequest("frozen-run", "ignored", dataset, 1000.0, strategy, cost)

    result = BacktestEngine().run(request)

    # 8 bps at each fill; first signal is at bar 0 close, buy is bar 1 open.
    assert [(t.side, t.price) for t in result.trades] == [("buy", 50), ("sell", 70)]
    assert result.trades[0].cost == pytest.approx(0.8)
    assert result.trades[0].quantity == pytest.approx(19.984)
    assert result.trades[1].cost == pytest.approx(1.119104)
    assert result.equity_curve == pytest.approx((1000, 1199.04, 1397.760896))
    assert result.exit_status == "SUCCEEDED"
    assert result.data_hash == dataset.dataset_hash

    rerun = BacktestEngine().run(request)
    assert rerun == result
    assert result.equity_curve_hash == rerun.equity_curve_hash


def test_golden_strategy_json_roundtrip_keeps_execution() -> None:
    strategy, dataset = _fixture()
    normalized = StrategyIR.model_validate_json(strategy.model_dump_json(by_alias=True))
    assert normalized == strategy
    assert normalized.entry.conditions == [
        Condition(op="greater_than", left="close", value=0)
    ]
    first = BacktestEngine().run(BacktestRequest("same", "ignored", dataset, 1000, strategy))
    second = BacktestEngine().run(BacktestRequest("same", "ignored", dataset, 1000, normalized))
    assert first == second
