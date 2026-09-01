from __future__ import annotations

import pytest

from core.costs.model import CostModel, TradeCost
from core.costs.slippage import SlippageModel


def test_cost_model_applies_commission_spread_and_slippage() -> None:
    model = CostModel("cost-v1", commission_bps=10, spread_bps=4, slippage=SlippageModel(5))

    cost = model.calculate(10_000, side="buy", stress_multiplier=1.0)

    assert isinstance(cost, TradeCost)
    assert cost.total == pytest.approx(19.0)
    assert cost.version == "cost-v1"
    assert model.calculate(10_000, side="buy", stress_multiplier=2.0).total > cost.total
