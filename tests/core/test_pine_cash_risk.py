import pytest

from core.features.pine_cash_risk import cash_risk_levels


@pytest.mark.parametrize(
    "qty,stop,target",
    [
        (2.0, 95.0, 110.0),
        (-2.0, 105.0, 90.0),
    ],
)
def test_signed_risk_levels_and_cash_limits(qty, stop, target):
    x = cash_risk_levels(
        avg_entry_price=100,
        signed_quantity=qty,
        point_value=10,
        tick_size=0.25,
        stop_budget=100,
        target_budget=200,
    )
    assert x.stop_price == stop
    assert x.target_price == target
    assert x.stop_cash == 100
    assert x.target_cash == 200


def test_cash_budget_rounds_down_to_whole_ticks():
    x = cash_risk_levels(
        avg_entry_price=100,
        signed_quantity=3,
        point_value=1,
        tick_size=0.5,
        stop_budget=10,
        target_budget=11,
    )
    assert x.stop_ticks == 6
    assert x.target_ticks == 7
    assert x.stop_cash <= 10
    assert x.target_cash <= 11


@pytest.mark.parametrize(
    "updates",
    [
        {"signed_quantity": 0},
        {"point_value": 0},
        {"tick_size": 0},
        {"stop_budget": -1},
        {"target_budget": float("nan")},
        {"stop_budget": 0.1},
    ],
)
def test_invalid_inputs_fail_closed(updates):
    args = dict(
        avg_entry_price=100.0,
        signed_quantity=2.0,
        point_value=10.0,
        tick_size=0.25,
        stop_budget=100.0,
        target_budget=200.0,
    )
    args.update(updates)
    with pytest.raises(ValueError):
        cash_risk_levels(**args)
