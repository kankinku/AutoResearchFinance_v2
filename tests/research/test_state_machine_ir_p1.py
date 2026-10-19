"""P1-2: stateful typed events must be causal, bounded and research-only."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.expression_ir import ExpressionError
from research.indicator_engine.state_machine_ir import (
    compile_state_machine,
    development_state_signal_vector,
    evaluate_state_machine,
    state_signal_vector,
)
from strategy_ir.schema import StrategyIR


def source(name="close"):
    return {"op": "source", "name": name}


def constant(value):
    return {"op": "const", "value": float(value)}


def condition(op, *args, **kwargs):
    return {"op": op, "args": list(args), **kwargs}


def plan(*, signal_mode="transition"):
    return {
        "machine_id": "confirm_then_fire",
        "states": [
            {"name": "idle"},
            {"name": "armed", "timeout_bars": 3, "timeout_to": "idle"},
            {"name": "fired"},
        ],
        "initial_state": "idle",
        "transitions": [
            {
                "transition_id": "arm",
                "from_state": "idle",
                "to_state": "armed",
                "when": condition("gt", source(), constant(10)),
            },
            {
                "transition_id": "confirm",
                "from_state": "armed",
                "to_state": "fired",
                "when": condition("gt", source(), constant(11)),
            },
            {
                "transition_id": "return_idle",
                "from_state": "fired",
                "to_state": "idle",
                "when": condition("lt", source(), constant(9)),
            },
        ],
        "reset_when": source("reset"),
        **(
            {"signal_on_transitions": ["confirm"]}
            if signal_mode == "transition"
            else {"signal_on_states": ["fired"]}
        ),
    }


def compile_plan(definition=None):
    return compile_state_machine(
        plan() if definition is None else definition,
        {"close": "number", "reset": "boolean"},
    )


def test_arm_confirm_fire_one_step_per_completed_bar() -> None:
    compiled = compile_plan()
    result = evaluate_state_machine(
        compiled,
        {
            "close": [8, 12, 13, 13, 8, 12, 13],
            "reset": [False] * 7,
        },
    )
    assert result.states == (
        "idle",
        "armed",
        "fired",
        "fired",
        "idle",
        "armed",
        "fired",
    )
    assert result.transition_ids == (
        None,
        "arm",
        "confirm",
        None,
        "return_idle",
        "arm",
        "confirm",
    )
    assert result.signals == (0, 0, 1, 0, 0, 0, 1)
    assert state_signal_vector(
        compiled, {"close": [8, 12, 13, 13, 8, 12, 13], "reset": [False] * 7}
    ) == (
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    assert result.trace_hash


def test_state_based_signal_and_reset_take_priority() -> None:
    compiled = compile_plan(plan(signal_mode="state"))
    result = evaluate_state_machine(
        compiled,
        {
            "close": [8, 12, 13, 14, 14, 12, 13],
            "reset": [False, False, False, False, True, False, False],
        },
    )
    assert result.states == ("idle", "armed", "fired", "fired", "idle", "armed", "fired")
    assert result.signals == (0, 0, 1, 1, 0, 0, 1)
    assert result.transition_ids[4] == "__reset__"


def test_timeout_expires_before_guard_and_does_not_invent_event_signal() -> None:
    compiled = compile_plan()
    # Armed at t1, timeout=3: t2,t3 continue, expires before any guard on t4.
    result = evaluate_state_machine(
        compiled,
        {
            "close": [8, 12, 10, 10, 13, 12, 13],
            "reset": [False] * 7,
        },
    )
    assert result.states[1:5] == ("armed", "armed", "armed", "idle")
    assert result.transition_ids[4] == "__timeout__"
    assert result.signals[4] == 0
    assert result.transition_ids[5] == "arm"
    assert result.transition_ids[6] == "confirm"


def test_unknown_input_halts_decision_without_treating_missing_as_false() -> None:
    compiled = compile_plan()
    result = evaluate_state_machine(
        compiled,
        {
            "close": [12, None, 13, 8, 12, 13],
            "reset": [False] * 6,
        },
    )
    assert result.signals == (0, None, 1, 0, 0, 1)
    assert result.states[1] == "armed"
    assert result.transition_ids[1] == "__unknown__"
    assert result.states[2] == "fired"
    assert result.signals[2] == 1


def test_missing_reset_signal_must_fail_closed_for_every_state() -> None:
    result = evaluate_state_machine(
        compile_plan(),
        {"close": [12, 13, 13], "reset": [False, None, False]},
    )
    assert result.signals == (0, None, 1)
    assert result.transition_ids[1] == "__unknown__"
    assert result.states == ("armed", "armed", "fired")


def test_ordered_transitions_choose_first_when_multiple_guards_are_true() -> None:
    candidate = plan()
    candidate["transitions"].insert(
        0,
        {
            "transition_id": "first",
            "from_state": "idle",
            "to_state": "fired",
            "when": condition("gt", source(), constant(10)),
        },
    )
    candidate["signal_on_transitions"] = ["first"]
    compiled = compile_plan(candidate)
    result = evaluate_state_machine(compiled, {"close": [12], "reset": [False]})
    assert result.states == ("fired",)
    assert result.transition_ids == ("first",)
    assert result.signals == (1,)


def test_prefix_replay_and_last_bar_change_do_not_repaint_earlier_decisions() -> None:
    compiled = compile_plan()
    series = {
        "close": [8, 12, 13, 12, 8, 13, 14, 8, 11, 12, 9, 12],
        "reset": [False] * 12,
    }
    expected = evaluate_state_machine(compiled, series)
    for cutoff in (1, 2, 4, 8):
        portion = {key: value[:cutoff] for key, value in series.items()}
        reduced = evaluate_state_machine(compiled, portion)
        assert reduced.signals == expected.signals[:cutoff]
        assert reduced.states == expected.states[:cutoff]
    series["close"][-1] = 1000
    revised = evaluate_state_machine(compiled, series)
    assert revised.signals[:-1] == expected.signals[:-1]
    assert revised.states[:-1] == expected.states[:-1]


@pytest.mark.parametrize(
    "update",
    [
        {"initial_state": "missing"},
        {"states": [{"name": "idle"}, {"name": "idle"}]},
        {"states": [{"name": "idle", "timeout_bars": 2}]},
        {"states": [{"name": "idle", "timeout_to": "idle"}]},
        {"states": [{"name": "idle", "timeout_bars": 0, "timeout_to": "idle"}]},
        {"signal_on_transitions": []},
        {"signal_on_states": ["idle"]},
        {"signal_on_transitions": ["missing"]},
        {"reset_when": {"op": "python", "command": "print(1)"}},
        {
            "transitions": [
                {
                    "transition_id": "a",
                    "from_state": "armed",
                    "to_state": "missing",
                    "when": source("reset"),
                }
            ]
        },
        {
            "transitions": [
                {
                    "transition_id": "a",
                    "from_state": "armed",
                    "to_state": "armed",
                    "when": source("close"),
                }
            ]
        },
        {"machine_id": "A script();"},
    ],
)
def test_invalid_state_machine_rejected(update) -> None:
    candidate = plan()
    candidate.update(update)
    with pytest.raises((ExpressionError, ValueError)):
        compile_plan(candidate)


def test_non_boolean_transition_guard_and_unbounded_total_cost_rejected() -> None:
    candidate = plan()
    candidate["transitions"][0]["when"] = source()
    with pytest.raises(ExpressionError, match="boolean"):
        compile_plan(candidate)
    oversized = plan()
    oversized["transitions"] = oversized["transitions"] * 12
    with pytest.raises(ExpressionError):
        compile_plan(oversized)


def test_forged_compilation_wrong_types_and_nonfinite_inputs_rejected() -> None:
    compiled = compile_plan()
    values = {"close": [12, 13], "reset": [False, False]}
    with pytest.raises(ExpressionError, match="stale|forged"):
        evaluate_state_machine(replace(compiled, definition_hash="x"), values)
    with pytest.raises(ExpressionError, match="source type mismatch"):
        evaluate_state_machine(compiled, {"close": [12, 13], "reset": [0, 1]})
    with pytest.raises(ExpressionError, match="nonfinite"):
        evaluate_state_machine(compiled, {"close": [float("nan"), 13], "reset": [False, False]})
    with pytest.raises(ExpressionError, match="length"):
        evaluate_state_machine(compiled, {"close": [12], "reset": [False, False]})
    with pytest.raises(ExpressionError, match="names"):
        evaluate_state_machine(compiled, {"close": [12], "reset": [False], "lookahead": [0]})


def _market(zone=DataZone.DEVELOPMENT, *, final=11) -> MarketDataSet:
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    prices = (8, 12, 13, 13, 8, 12, 13, 8, 12, 13, final)
    return MarketDataSet(
        "state_machine_synthetic",
        zone,
        tuple(
            Bar(t0 + timedelta(days=i), "QQQ", float(c), c + 1, c - 1, float(c), 1000)
            for i, c in enumerate(prices)
        ),
    )


def _market_plan():
    machine = plan()
    machine["reset_when"] = condition("lt", source(), constant(0))
    return compile_state_machine(machine, {"close": "number"})


def test_development_adapter_denies_sealed_data_and_external_source() -> None:
    compiled = _market_plan()
    with pytest.raises(ExpressionError, match="DEVELOPMENT"):
        development_state_signal_vector(compiled, _market(DataZone.SEALED_OOS))
    with pytest.raises(ExpressionError, match="external"):
        development_state_signal_vector(compile_plan(), _market())


def test_canonical_backtest_only_fills_state_event_after_completed_close() -> None:
    machine = _market_plan()
    market = _market()
    signals = development_state_signal_vector(machine, market)
    parent = StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "state_machine_fixture",
            "family": "research",
            "generation": 0,
            "indicators": {"baseline": {"type": "SMA", "period": 2}},
            "features": {"state_event": {"feature_id": "test_only_state_event"}},
            "entry": {
                "logic": "AND",
                "conditions": [
                    {"op": "greater_than", "left": "state_event", "value": 0.5},
                ],
            },
            "exit": {
                "logic": "AND",
                "conditions": [
                    {"op": "less_equal", "left": "state_event", "value": 0.5},
                ],
            },
            "risk": {"stop_loss_pct": 0, "take_profit_pct": 0},
        }
    )
    request = BacktestRequest(
        run_id="p1-2-causal",
        strategy_hash="test-only",
        dataset=market,
        initial_cash=10000,
        strategy=parent,
        feature_values={"state_event": signals},
    )
    result = BacktestEngine().run(request)
    assert result.exit_status == "SUCCEEDED"
    assert result.equity_curve_hash == BacktestEngine().run(request).equity_curve_hash
    assert len(result.trades) > 1
    for trade in result.trades:
        t = next(
            i for i, bar in enumerate(market.bars) if bar.timestamp.isoformat() == trade.timestamp
        )
        assert t > 0
        assert signals[t - 1] == (1.0 if trade.side == "buy" else 0.0)


def test_constant_guard_uses_explicit_bounded_bar_count() -> None:
    """A constant expression needs an explicit bar count; it cannot invent a timeline."""
    constant_plan = {
        "machine_id": "constant_event",
        "states": [{"name": "idle"}, {"name": "active"}],
        "initial_state": "idle",
        "transitions": [
            {
                "transition_id": "activate",
                "from_state": "idle",
                "to_state": "active",
                "when": {"op": "const", "value": True},
            },
        ],
        "signal_on_transitions": ["activate"],
    }
    compiled = compile_state_machine(constant_plan, {})
    with pytest.raises(ExpressionError, match="bar count"):
        evaluate_state_machine(compiled, {})
    result = evaluate_state_machine(compiled, {}, bar_count=5)
    assert result.signals == (1, 0, 0, 0, 0)
    assert result.states == ("active",) * 5
    assert result.transition_ids == ("activate", None, None, None, None)


def test_unknown_from_inactive_state_does_not_suppress_relevant_decision() -> None:
    compiled = compile_plan()
    result = evaluate_state_machine(
        compiled,
        {"close": [8, 8], "reset": [False, False]},
    )
    # An inactive armed->fired guard is irrelevant until 'armed' becomes active.
    assert result.signals == (0, 0)
    assert result.states == ("idle", "idle")


def test_reset_priority_over_timeout_and_due_transition() -> None:
    definition = plan()
    definition["states"][1]["timeout_bars"] = 1
    compiled = compile_plan(definition)
    result = evaluate_state_machine(
        compiled,
        {"close": [12, 13, 13], "reset": [False, True, False]},
    )
    assert result.states == ("armed", "idle", "armed")
    assert result.transition_ids == ("arm", "__reset__", "arm")
    assert result.signals == (0, 0, 0)


def test_market_prefix_stable_state_signals_with_delayed_last_bar() -> None:
    compiled = _market_plan()
    all_bars = _market().bars
    full = development_state_signal_vector(compiled, _market())
    for cutoff in (3, 5, 8):
        earlier = MarketDataSet("state_machine_synthetic", DataZone.DEVELOPMENT, all_bars[:cutoff])
        assert development_state_signal_vector(compiled, earlier) == full[:cutoff]
    assert development_state_signal_vector(compiled, _market(final=200))[:-1] == full[:-1]


def test_forged_state_flag_fails_closed() -> None:
    compiled = compile_plan()
    with pytest.raises(ExpressionError, match="forged|stale|type mismatch"):
        evaluate_state_machine(
            replace(compiled, source_types=(("close", "boolean"), ("reset", "boolean"))),
            {"close": [12], "reset": [False]},
        )


def test_state_sourceless_constant_expression_rejects_oversized_bars() -> None:
    candidate = {
        "machine_id": "sourcefree",
        "states": [{"name": "idle"}, {"name": "active"}],
        "initial_state": "idle",
        "transitions": [
            {
                "transition_id": "run",
                "from_state": "idle",
                "to_state": "active",
                "when": {"op": "const", "value": True},
            },
        ],
        "signal_on_states": ["active"],
    }
    compiled = compile_state_machine(candidate, {})
    with pytest.raises(ExpressionError, match="unbounded"):
        evaluate_state_machine(compiled, {}, bar_count=20001)
