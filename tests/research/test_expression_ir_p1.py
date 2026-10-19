"""P1-1: a typed, independent expression language; no live IR mutation."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.expression_ir import (
    ExpressionError,
    compile_expression,
    development_signal_vector,
    evaluate_expression,
    signal_vector,
)
from strategy_ir.schema import StrategyIR


def src(name: str = "close") -> dict:
    return {"op": "source", "name": name}


def number(value: float) -> dict:
    return {"op": "const", "value": value}


def expr(op: str, *args: dict, **kwargs) -> dict:
    return {"op": op, "args": list(args), **kwargs}


def fixture_market(zone: DataZone = DataZone.DEVELOPMENT, *, changing_last: bool = False):
    t0 = datetime(2021, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(90):
        price = 100.0 + 7 * math.sin(i / 2)
        if i == 89 and changing_last:
            price *= 2
        bars.append(Bar(t0 + timedelta(days=i), "QQQ", price, price + 2, price - 2, price, 1000.0))
    return MarketDataSet("p1_expr_synthetic", zone, tuple(bars))


def test_llm_json_arithmetic_nested_condition_and_development_signal() -> None:
    # The LLM is allowed to invent the arithmetic, not inject Python/Pine.
    plan = expr(
        "and",
        expr("gt", expr("div", src(), expr("rolling_mean", src(), window=3)), number(1.01)),
        expr("not", expr("lt", src(), number(80))),
    )
    compiled = compile_expression(plan, {"close": "number"})
    assert compiled.result_type == "boolean"
    assert not compiled.broker_executable
    assert compiled.status == "DEVELOPMENT_ONLY"
    signal = development_signal_vector(compiled, fixture_market())
    assert signal[:2] == (None, None)
    assert any(item == 1 for item in signal if item is not None)
    assert any(item == 0 for item in signal if item is not None)


def test_confirmed_cross_and_explicit_past_lag() -> None:
    candidate = expr(
        "and",
        expr("cross_above", src(), number(10.0)),
        expr("gt", src(), expr("lag", src(), periods=2)),
    )
    compiled = compile_expression(candidate, {"close": "number"})
    assert evaluate_expression(compiled, {"close": [8.0, 9.0, 11.0, 12.0, 9.0, 13.0]}) == (
        None,
        None,
        True,
        False,
        False,
        True,
    )


def test_boolean_lag_if_else_and_arithmetic_are_typed() -> None:
    candidate = expr(
        "if_else",
        expr("lag", src("switch"), periods=1),
        expr("add", src("close"), number(2)),
        expr("sub", src("close"), number(1)),
    )
    compiled = compile_expression(candidate, {"close": "number", "switch": "boolean"})
    assert compiled.result_type == "number"
    values = evaluate_expression(
        compiled, {"close": [10.0, 11.0, 12.0, 13.0], "switch": [False, True, None, False]}
    )
    assert values == (None, 10.0, 14.0, None)
    with pytest.raises(ExpressionError, match="entry signal must be boolean"):
        signal_vector(compiled, {"close": (10.0,), "switch": (True,)})


def test_division_by_zero_and_missing_stay_missing() -> None:
    compiled = compile_expression(
        expr("div", src(), src("denominator")),
        {"close": "number", "denominator": "number"},
    )
    assert evaluate_expression(
        compiled, {"close": [10.0, None, 20.0], "denominator": [0, 2.0, 4.0]}
    ) == (None, None, 5.0)


def test_completed_prefix_stability_for_four_different_expressions() -> None:
    candidates = [
        expr("gt", src(), number(100)),
        expr("gt", expr("rolling_mean", src(), window=5), number(99)),
        expr(
            "or",
            expr("lt", expr("sub", src(), expr("lag", src(), periods=2)), number(0)),
            expr("gt", src(), number(110)),
        ),
        expr("cross_below", src(), expr("rolling_mean", src(), window=4)),
    ]
    close = [100 + math.sin(i / 2) * 5 for i in range(80)]
    for candidate in candidates:
        compiled = compile_expression(candidate, {"close": "number"})
        all_results = evaluate_expression(compiled, {"close": close})
        for prefix in (7, 23, 41, 69):
            truncated = evaluate_expression(compiled, {"close": close[:prefix]})
            assert truncated == all_results[:prefix]
        updated = close[:-1] + [200.0]
        after = evaluate_expression(compiled, {"close": updated})
        assert after[:-1] == all_results[:-1]


@pytest.mark.parametrize(
    "candidate,declarations",
    [
        ({"op": "python", "code": "__import__('os')"}, {"close": "number"}),
        ({"op": "source", "name": "not_registered"}, {"close": "number"}),
        (expr("add", src(), number(True)), {"close": "number"}),
        (expr("and", src(), src()), {"close": "number"}),
        (expr("if_else", src(), number(1), number(2)), {"close": "number"}),
        (
            expr("if_else", expr("gt", src(), number(1)), number(2), expr("gt", src(), number(3))),
            {"close": "number"},
        ),
        (expr("eq", src(), expr("gt", src(), number(3))), {"close": "number"}),
        (expr("lag", src(), periods=0), {"close": "number"}),
        (expr("lag", src(), periods=-1), {"close": "number"}),
        (expr("rolling_mean", src(), window=0), {"close": "number"}),
        (expr("div", src(), number(float("inf"))), {"close": "number"}),
        ({"op": "source", "name": "close", "forward": 10}, {"close": "number"}),
        ({"op": "const", "value": float("nan")}, {}),
    ],
)
def test_compiler_fails_closed(candidate, declarations) -> None:
    with pytest.raises(ExpressionError):
        compile_expression(candidate, declarations)


def test_expression_complexity_budget_and_cumulative_lookback() -> None:
    deep = src()
    for _ in range(9):
        deep = expr("lag", deep, periods=1)
    with pytest.raises(ExpressionError, match="complexity"):
        compile_expression(deep, {"close": "number"})

    heavy = src()
    for _ in range(7):
        heavy = expr("add", heavy, heavy)
    with pytest.raises(ExpressionError, match="complexity"):
        compile_expression(heavy, {"close": "number"})

    long_lag = expr("lag", expr("lag", src(), periods=300), periods=300)
    with pytest.raises(ExpressionError, match="lookback"):
        compile_expression(long_lag, {"close": "number"})


def test_source_type_and_forged_compiled_expression_blocked() -> None:
    compiled = compile_expression(src("flag"), {"flag": "boolean"})
    with pytest.raises(ExpressionError, match="source type mismatch"):
        evaluate_expression(compiled, {"flag": [1.0]})
    with pytest.raises(ExpressionError, match="source names"):
        evaluate_expression(compiled, {"flag": [True], "surprise": [True]})
    with pytest.raises(ExpressionError, match="source series length mismatch"):
        evaluate_expression(
            compile_expression(
                expr("and", src("flag"), src("other")), {"flag": "boolean", "other": "boolean"}
            ),
            {"flag": [True], "other": [True, False]},
        )
    with pytest.raises(ExpressionError, match="stale"):
        evaluate_expression(replace(compiled, definition_hash="f" * 64), {"flag": [True]})
    with pytest.raises(ExpressionError, match="unbounded"):
        evaluate_expression(compiled, {"flag": [True] * 20_001})
    with pytest.raises(ExpressionError, match="invalid numeric source"):
        evaluate_expression(compile_expression(src(), {"close": "number"}), {"close": [True]})
    with pytest.raises(ExpressionError, match="nonfinite"):
        evaluate_expression(
            compile_expression(src(), {"close": "number"}), {"close": [float("nan")]}
        )


def test_sealed_and_unverified_external_sources_cannot_enter_development_adapter() -> None:
    compiled = compile_expression(expr("gt", src(), number(101)), {"close": "number"})
    with pytest.raises(ExpressionError, match="DEVELOPMENT"):
        development_signal_vector(compiled, fixture_market(DataZone.SEALED_OOS))
    with pytest.raises(ExpressionError, match="external"):
        development_signal_vector(
            compile_expression(
                expr("gt", src("unknown_feature"), number(101)),
                {"unknown_feature": "number"},
            ),
            fixture_market(),
        )


def test_canonical_costed_backtest_uses_previous_completed_signal_on_next_open() -> None:
    # P1-1 is not in the autonomous provider or registry. Test only a vetted
    # synthetic adapter boundary with the unchanged canonical backtester.
    candidate = expr("gt", src(), expr("rolling_mean", src(), window=3))
    compiled = compile_expression(candidate, {"close": "number"})
    market = fixture_market()
    signal = development_signal_vector(compiled, market)
    parent = StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "p1_expression_experiment",
            "family": "research",
            "generation": 0,
            "indicators": {"baseline": {"type": "SMA", "period": 2}},
            "features": {"experimental_expression": {"feature_id": "expression_fixture"}},
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"op": "greater_than", "left": "experimental_expression", "value": 0.5},
                ],
            },
            "exit": {
                "logic": "AND",
                "conditions": [
                    {"op": "less_equal", "left": "experimental_expression", "value": 0.5},
                ],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )
    request = BacktestRequest(
        run_id="p1-expression",
        strategy_hash="unhashed",
        dataset=market,
        initial_cash=10000,
        strategy=parent,
        feature_values={"experimental_expression": signal},
    )
    result = BacktestEngine().run(request)
    again = BacktestEngine().run(request)
    assert result.exit_status == "SUCCEEDED"
    assert result.trades == again.trades
    assert result.equity_curve_hash == again.equity_curve_hash
    assert len(result.trades) >= 2
    for trade in result.trades:
        t = next(
            i for i, bar in enumerate(market.bars) if bar.timestamp.isoformat() == trade.timestamp
        )
        assert t > 0
        assert signal[t - 1] == (1.0 if trade.side == "buy" else 0.0)
