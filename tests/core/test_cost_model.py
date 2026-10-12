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


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), -1.0])
@pytest.mark.parametrize("field", ["commission_bps", "spread_bps", "slippage_bps"])
def test_cost_model_rejects_negative_or_nonfinite_rates(field: str, invalid: float) -> None:
    props = {"commission_bps": 1.0, "spread_bps": 2.0, "slippage_bps": 3.0}
    props[field] = invalid
    with pytest.raises(ValueError, match="finite|negative"):
        CostModel(
            "cost-v1",
            commission_bps=props["commission_bps"],
            spread_bps=props["spread_bps"],
            slippage=SlippageModel(props["slippage_bps"]),
        )


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_cost_model_rejects_nonfinite_stress_and_notional(invalid: float) -> None:
    model = CostModel("cost-v1", 1.0, 2.0, SlippageModel(3.0))
    with pytest.raises(ValueError, match="finite"):
        model.calculate(1000.0, side="buy", stress_multiplier=invalid)
    with pytest.raises(ValueError, match="finite"):
        model.calculate(invalid, side="sell", stress_multiplier=1.0)


def test_cost_model_rejects_numeric_overflow_before_trade() -> None:
    model = CostModel("cost-v1", 1e300, 1.0, SlippageModel(1.0))
    with pytest.raises(ValueError, match="finite"):
        model.calculate(1e300, side="buy", stress_multiplier=1.0)
