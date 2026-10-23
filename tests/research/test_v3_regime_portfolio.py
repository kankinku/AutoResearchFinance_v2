"""V3 development-only shared-cash, per-sleeve route execution regressions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import Bar, MarketDataSet
from research.llm.regime_portfolio_v3 import (
    RegimePortfolioError,
    simulate_regime_portfolio,
)
from research.llm.regime_router_v3 import RegimeRouterSpec, RegimeRouteSpec
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture


def _dataset():
    base = datetime(2024, 1, 2, tzinfo=timezone.utc)
    bars = tuple(
        Bar(base + timedelta(days=n), "QQQ", 100, 101, 99, 100, 1000)
        for n in range(8)
    )
    return MarketDataSet("v3-regimes-development", "development", bars)


def _strategy(name: str, exit_feature="exit"):
    base, _ = _warmup_fixture()
    return base.strategy.model_copy(update={
        "strategy_id": name,
        "entry": base.strategy.entry.model_copy(update={
            "conditions": [base.strategy.entry.conditions[0].model_copy(update={
                "left": "entry", "op": "greater_than", "value": 0.5,
            })]
        }),
        "exit": base.strategy.exit.model_copy(update={
            "conditions": [base.strategy.exit.conditions[0].model_copy(update={
                "left": exit_feature, "op": "greater_than", "value": 0.5,
            })]
        }),
    })


def _program(mode: str = "exclusive", size_a=50.0, size_b=50.0,
             transition="flatten_on_switch"):
    from strategy_ir.schema import RuleSet
    return RegimeRouterSpec(
        mode=mode,
        transition_policy=transition,
        routes=(
            RegimeRouteSpec(
                name="bull",
                when=RuleSet.model_validate({
                    "logic": "AND",
                    "conditions": [{"op": "greater_than", "left": "trend", "value": 0.5}],
                }),
                strategy_id="alpha",
                allocation_pct=size_a,
            ),
            RegimeRouteSpec(
                name="bear",
                when=RuleSet.model_validate({
                    "logic": "AND",
                    "conditions": [{"op": "less_equal", "left": "trend", "value": 0.5}],
                }),
                strategy_id="beta",
                allocation_pct=size_b,
            ),
        ),
    )


COST = CostModel("regime-cost-test-v1", 1.0, 2.0, SlippageModel(5.0))


def test_exclusive_switch_next_open_and_internal_netting_single_cash():
    result = simulate_regime_portfolio(
        market=_dataset(),
        program=_program(),
        strategies={"alpha": _strategy("alpha"), "beta": _strategy("beta")},
        values={
            "trend": [1, 1, 0, 0, 0, 0, 0, 0],
            "entry": [1] * 8, "exit": [0] * 8,
        },
        cost_model=COST,
        initial_cash=10000,
    )
    assert result.status == "DEVELOPMENT_ONLY"
    assert result.equity_curve
    assert result.equity_curve[0] == 10000
    assert [(f.strategy_id, f.side, f.bar_index) for f in result.sleeve_fills] == [
        ("alpha", "buy", 1), ("alpha", "sell", 3), ("beta", "buy", 3),
    ]
    # Route switch at close of bar 2 is never executed at bar 2 open.
    assert [f.signal_bar_index for f in result.sleeve_fills] == [0, 2, 2]
    assert len(result.external_trades) == 2  # initial buy + ONE netted switch
    assert result.external_trades[1].gross_notional < 10.0
    assert result.total_costs < 5.0
    assert all(c >= -1e-8 for c in result.cash_curve)
    assert result.equity_curve[-1] < 10000
    assert result.trace_hash


def test_weighted_two_sleeves_share_one_external_buy_and_cash_limit():
    from strategy_ir.schema import RuleSet
    always = RuleSet.model_validate({
        "logic": "AND",
        "conditions": [{"op": "greater_than", "left": "trend", "value": 0.5}],
    })
    program = RegimeRouterSpec(mode="weighted", routes=(
        RegimeRouteSpec(name="a", when=always, strategy_id="alpha", allocation_pct=60),
        RegimeRouteSpec(name="b", when=always, strategy_id="beta", allocation_pct=40),
    ))
    result = simulate_regime_portfolio(
        market=_dataset(),
        program=program,
        strategies={"alpha": _strategy("alpha"), "beta": _strategy("beta")},
        values={"trend": [1]*8, "entry": [1]*8, "exit": [0]*8},
        cost_model=COST,
    )
    assert len(result.external_trades) == 1
    assert result.external_trades[0].side == "buy"
    assert len(result.sleeve_fills) == 2
    assert sum(x.gross_notional for x in result.sleeve_fills) <= 10000 + 1e-9
    assert all(x >= -1e-8 for x in result.cash_curve)
    assert sum(x.quantity for x in result.sleeve_fills) * 100 < 10000
    assert result.external_trades[0].cost == pytest.approx(result.total_costs)


def test_invalid_regime_data_risk_or_unapproved_market_fails_closed():
    bad_strategy = _strategy("alpha").model_copy(update={
        "risk": _strategy("alpha").risk.model_copy(update={"max_concurrent_positions": 2})
    })
    kwargs = {
        "market": _dataset(),
        "program": _program(),
        "strategies": {"alpha": bad_strategy, "beta": _strategy("beta")},
        "values": {"trend": [1]*8, "entry": [1]*8, "exit": [0]*8},
        "cost_model": COST,
    }
    with pytest.raises(RegimePortfolioError, match="risk"):
        simulate_regime_portfolio(**kwargs)
    with pytest.raises(RegimePortfolioError, match="missing"):
        simulate_regime_portfolio(**{**kwargs, "strategies": {
            "alpha": _strategy("alpha"), "beta": _strategy("beta")},
            "values": {"trend": [1]*8, "entry": [1]*8},
        })
    altered = replace(_dataset(), zone="sealed_oos")
    with pytest.raises(RegimePortfolioError, match="development"):
        simulate_regime_portfolio(**{**kwargs, "market": altered,
            "strategies": {"alpha": _strategy("alpha"), "beta": _strategy("beta")}})


def test_replay_ledger_proof_reconciles_positions_cash_and_net_exchange_costs():
    from research.llm.regime_ledger_audit_v3 import audit_regime_ledger

    market = _dataset()
    kwargs = {
        "market": market,
        "program": _program(),
        "strategies": {"alpha": _strategy("alpha"), "beta": _strategy("beta")},
        "values": {"trend": [1, 1, 0, 0, 0, 0, 0, 0],
                   "entry": [1]*8, "exit": [0]*8},
        "cost_model": COST,
    }
    output = simulate_regime_portfolio(**kwargs)
    report = audit_regime_ledger(output, market, COST, initial_cash=10_000.0)
    assert report.verified_fills == len(output.sleeve_fills)
    assert report.external_costs == pytest.approx(output.total_costs)
    assert report.realized_final_equity == pytest.approx(output.equity_curve[-1])
    assert report.audit_hash


def test_ledger_audit_rejects_fake_cash_and_backdated_fills():
    from research.llm.regime_ledger_audit_v3 import (
        RegimeLedgerError,
        audit_regime_ledger,
    )

    market = _dataset()
    output = simulate_regime_portfolio(
        market=market,
        program=_program(),
        strategies={"alpha": _strategy("alpha"), "beta": _strategy("beta")},
        values={"trend": [1, 1, 0, 0, 0, 0, 0, 0],
                "entry": [1]*8, "exit": [0]*8},
        cost_model=COST,
    )
    with pytest.raises(RegimeLedgerError, match="cash"):
        audit_regime_ledger(
            replace(output, cash_curve=(99,) + output.cash_curve[1:]),
            market, COST, initial_cash=10_000.0,
        )
    first = output.sleeve_fills[0]
    bad = replace(first, signal_bar_index=first.bar_index)
    with pytest.raises(RegimeLedgerError, match="next.open"):
        audit_regime_ledger(
            replace(output, sleeve_fills=(bad,) + output.sleeve_fills[1:]),
            market, COST, initial_cash=10_000.0,
        )


def test_composite_child_can_act_as_one_regime_sleeve():
    from core.integrity.hashes import content_hash
    from research.llm.composite_crossover_v3 import VerifiedDonor, compose
    from strategy_ir.schema import RuleSet

    base = _strategy("baseline")
    donors = []
    for generation, percent in ((20, 100), (21, 100), (22, 40)):
        ir = base.model_copy(update={
            "strategy_id": f"parent-{generation}", "generation": generation,
            "risk": base.risk.model_copy(update={"position_size_pct": percent}),
        })
        donors.append(VerifiedDonor(
            generation, f"{generation:064x}", f"{generation+1:064x}", ir,
            content_hash(ir.model_dump(mode="json", by_alias=True)), True,
        ))
    composite = compose(entry=donors[0], exit=donors[1], risk=donors[2])
    ir = composite.strategy
    program = RegimeRouterSpec(mode="exclusive", routes=(
        RegimeRouteSpec(
            name="combined", strategy_id=ir.strategy_id, allocation_pct=100,
            when=RuleSet.model_validate({"logic":"AND","conditions":[{
                "op":"greater_than", "left":"trend", "value":0.5,
            }]}),
        ),
    ))
    portfolio = simulate_regime_portfolio(
        market=_dataset(), program=program, strategies={ir.strategy_id: ir},
        values={"trend": [1]*8, "entry": [1]*8, "exit": [0]*8,
                "fast": [1]*8, "slow": [0]*8},
        cost_model=COST,
    )
    assert len(portfolio.sleeve_fills) == 1
    assert portfolio.sleeve_fills[0].gross_notional == pytest.approx(4000.0)
    assert portfolio.equity_curve[-1] < 10000.0
