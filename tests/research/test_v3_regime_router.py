"""V3 market-regime routing contract, not yet a trading/backtest engine."""

import pytest

from research.llm.regime_router_v3 import (
    RegimeRouterSpec,
    RegimeRouteSpec,
    resolve_regime_routes,
)


def _route(name, op, threshold, allocation):
    return RegimeRouteSpec.model_validate({
        "name": name,
        "when": {
            "logic": "AND",
            "conditions": [{"op": op, "left": "trend", "value": threshold}],
        },
        "strategy_id": "verified-" + name,
        "allocation_pct": allocation,
    })


def test_exclusive_route_uses_signal_bar_with_explicit_priority():
    up = _route("up", "greater_than", 0.5, 70)
    defensive = _route("defensive", "greater_than", 0.2, 20)
    program = RegimeRouterSpec(mode="exclusive", routes=(up, defensive))
    values = {"trend": [0.1, 0.3, 0.7, None]}
    assert resolve_regime_routes(program, values, 0) == ()
    active = resolve_regime_routes(program, values, 1)
    assert [(x.strategy_id, x.allocation_pct) for x in active] == [
        ("verified-defensive", 20)
    ]
    assert [x.strategy_id for x in resolve_regime_routes(program, values, 2)] == [
        "verified-up"
    ]
    assert resolve_regime_routes(program, values, 3) == ()


def test_weighted_routes_and_oversubscription_rejected():
    up = _route("up", "greater_than", 0.5, 60)
    defense = _route("defensive", "greater_than", 0.2, 40)
    program = RegimeRouterSpec(mode="weighted", routes=(up, defense))
    assert sum(x.allocation_pct for x in resolve_regime_routes(
        program, {"trend": [0.9]}, 0
    )) == 100
    with pytest.raises(ValueError, match="allocation"):
        RegimeRouterSpec(mode="weighted", routes=(
            up, defense.model_copy(update={"allocation_pct": 50}),
        ))
    with pytest.raises(ValueError, match="duplicate"):
        RegimeRouterSpec(mode="weighted", routes=(up, up))
    with pytest.raises(ValueError, match="missing"):
        resolve_regime_routes(program, {"other": [1]}, 0)
