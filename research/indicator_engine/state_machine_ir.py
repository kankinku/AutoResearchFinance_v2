"""P1-2: bounded causal state machines built from the generic expression IR.

Research-only feature calculation: does NOT register LLM operators, mutate
StrategyIR, execute orders, or permit sealed/other-timeframe observations.
A state at t is chosen after close(t), at most one transition per bar.
The existing canonical backtest decides how to fill at the next bar's open.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.expression_ir import (
    MAX_BARS,
    CompiledExpression,
    Expression,
    ExpressionError,
    Value,
    ValueType,
    compile_expression,
    evaluate_expression,
)

_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
MAX_STATES = 12
MAX_TRANSITIONS = 24
MAX_TOTAL_EXPR_NODES = 192
MAX_TIMEOUT = 500


class StateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    timeout_bars: int | None = Field(default=None, strict=True, ge=1, le=MAX_TIMEOUT)
    timeout_to: str | None = None

    @model_validator(mode="after")
    def valid_timeout(self) -> StateDefinition:
        if (self.timeout_bars is None) != (self.timeout_to is None):
            raise ValueError("timeout_bars and timeout_to must be provided together")
        if self.timeout_to is not None and not _ID.fullmatch(self.timeout_to):
            raise ValueError("invalid timeout state")
        return self


class StateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    transition_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    from_state: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    to_state: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    when: Expression


class StateMachinePlan(BaseModel):
    """Deterministic first-match priority, no arbitrary action or executable code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    machine_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    states: tuple[StateDefinition, ...] = Field(min_length=1, max_length=MAX_STATES)
    initial_state: str
    transitions: tuple[StateTransition, ...] = Field(min_length=1, max_length=MAX_TRANSITIONS)
    reset_when: Expression | None = None
    signal_on_transitions: tuple[str, ...] = ()
    signal_on_states: tuple[str, ...] = ()

    @model_validator(mode="after")
    def coherent_graph(self) -> StateMachinePlan:
        names = [state.name for state in self.states]
        allowed = set(names)
        if len(allowed) != len(names):
            raise ValueError("duplicate state names")
        if self.initial_state not in allowed:
            raise ValueError("missing initial state")
        ids = [item.transition_id for item in self.transitions]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate transition identifier")
        for item in self.transitions:
            if item.from_state not in allowed or item.to_state not in allowed:
                raise ValueError("transition refers to missing state")
        for state in self.states:
            if state.timeout_to is not None and state.timeout_to not in allowed:
                raise ValueError("timeout refers to missing state")
        if bool(self.signal_on_states) == bool(self.signal_on_transitions):
            raise ValueError("exactly one signal emission mode must be selected")
        if len(set(self.signal_on_states)) != len(self.signal_on_states):
            raise ValueError("duplicate emitted state")
        if len(set(self.signal_on_transitions)) != len(self.signal_on_transitions):
            raise ValueError("duplicate emitted transition")
        if any(name not in allowed for name in self.signal_on_states):
            raise ValueError("emitted state is not declared")
        if any(name not in set(ids) for name in self.signal_on_transitions):
            raise ValueError("emitted transition is not declared")
        return self


@dataclass(frozen=True)
class CompiledStateMachine:
    plan: StateMachinePlan
    source_types: tuple[tuple[str, ValueType], ...]
    definition_hash: str
    status: Literal["DEVELOPMENT_ONLY"] = "DEVELOPMENT_ONLY"
    broker_executable: Literal[False] = False


@dataclass(frozen=True)
class StateTrace:
    states: tuple[str, ...]
    transition_ids: tuple[str | None, ...]
    signals: tuple[int | None, ...]
    trace_hash: str
    status: Literal["NON_PIT_DEVELOPMENT_ONLY"] = "NON_PIT_DEVELOPMENT_ONLY"
    broker_executable: Literal[False] = False


def _node_count(expression: Expression) -> int:
    return 1 + sum(_node_count(child) for child in expression.args)


def compile_state_machine(
    plan: StateMachinePlan | Mapping[str, object],
    source_types: Mapping[str, ValueType],
) -> CompiledStateMachine:
    """Validate the graph, each guard's boolean type, and total compute budget."""
    try:
        raw = plan.model_dump(mode="json") if isinstance(plan, StateMachinePlan) else plan
        checked = StateMachinePlan.model_validate(raw)
    except (ValueError, TypeError, ValidationError) as exc:
        raise ExpressionError("invalid state machine schema") from exc
    guards = [item.when for item in checked.transitions]
    if checked.reset_when is not None:
        guards.append(checked.reset_when)
    if sum(_node_count(guard) for guard in guards) > MAX_TOTAL_EXPR_NODES:
        raise ExpressionError("state machine aggregate complexity budget exceeded")
    used: dict[str, ValueType] = {}
    for guard in guards:
        compiled = compile_expression(guard, source_types)
        if compiled.result_type != "boolean":
            raise ExpressionError("state machine guards must have boolean type")
        used.update(compiled.source_types)

    contract = tuple(sorted(used.items()))
    definition_hash = content_hash(
        {
            "machine": checked.model_dump(mode="json"),
            "source_types": contract,
            "contract": "bounded_state_machine_v1_development_only",
        }
    )
    return CompiledStateMachine(checked, contract, definition_hash)


def _compiled_guards(
    machine: CompiledStateMachine,
) -> tuple[dict[str, CompiledExpression], CompiledExpression | None]:
    types = dict(machine.source_types)
    guards = {
        item.transition_id: compile_expression(item.when, types)
        for item in machine.plan.transitions
    }
    reset = (
        compile_expression(machine.plan.reset_when, types)
        if machine.plan.reset_when is not None
        else None
    )
    return guards, reset


def evaluate_state_machine(
    machine: CompiledStateMachine,
    sources: Mapping[str, Sequence[Value]],
    *,
    bar_count: int | None = None,
) -> StateTrace:
    """Replay one deterministic state transition per completed observation.

    Missing active-state guard or missing global reset is UNKNOWN, never False.
    Unknown freezes the state and withholds that bar's trading signal. Reset
    takes precedence over expiry; expiry takes precedence over transitions.
    """
    verified = compile_state_machine(machine.plan, dict(machine.source_types))
    if (
        verified.definition_hash != machine.definition_hash
        or verified.source_types != machine.source_types
    ):
        raise ExpressionError("forged or stale compiled state machine")

    names = dict(machine.source_types)
    if set(sources) != set(names):
        raise ExpressionError("source names must match the compiled state machine")
    lengths = {len(value) for value in sources.values()}
    if len(lengths) > 1:
        raise ExpressionError("source series length mismatch")
    count = lengths.pop() if lengths else bar_count
    if type(count) is not int or not 1 <= count <= MAX_BARS:
        raise ExpressionError("missing or unbounded bar count")
    if bar_count is not None and (type(bar_count) is not int or bar_count != count):
        raise ExpressionError("bar count does not match input series")

    guards, reset = _compiled_guards(machine)

    def observe(expression: CompiledExpression) -> tuple[Value, ...]:
        observations = {name: sources[name] for name, _ in expression.source_types}
        return evaluate_expression(expression, observations, bar_count=count)

    transitions = {name: observe(guard) for name, guard in guards.items()}
    reset_values = observe(reset) if reset is not None else (False,) * count
    by_state: dict[str, list[StateTransition]] = {item.name: [] for item in machine.plan.states}
    state_defs = {item.name: item for item in machine.plan.states}
    for item in machine.plan.transitions:
        by_state[item.from_state].append(item)

    current = machine.plan.initial_state
    entered_at = 0
    observed_states: list[str] = []
    observed_events: list[str | None] = []
    decisions: list[int | None] = []
    emit_transitions = set(machine.plan.signal_on_transitions)
    emit_states = set(machine.plan.signal_on_states)

    for t in range(count):
        event: str | None = None
        signal: int | None
        if reset_values[t] is None:
            event, signal = "__unknown__", None
        elif reset_values[t] is True:
            current, entered_at = machine.plan.initial_state, t
            event, signal = "__reset__", 0
        else:
            state = state_defs[current]
            if state.timeout_bars is not None and t - entered_at >= state.timeout_bars:
                assert state.timeout_to is not None
                current, entered_at = state.timeout_to, t
                event, signal = "__timeout__", 0
            else:
                event = None
                signal = 0
                for transition in by_state[current]:
                    decision = transitions[transition.transition_id][t]
                    if decision is None:
                        event, signal = "__unknown__", None
                        break
                    if decision is True:
                        current, entered_at = transition.to_state, t
                        event = transition.transition_id
                        break
                if signal is not None:
                    signal = int(
                        event in emit_transitions if emit_transitions else current in emit_states
                    )
        observed_states.append(current)
        observed_events.append(event)
        decisions.append(signal)

    states = tuple(observed_states)
    events = tuple(observed_events)
    signals = tuple(decisions)
    trace_hash = content_hash(
        {
            "definition_hash": machine.definition_hash,
            "states": states,
            "events": events,
            "signals": signals,
        }
    )
    return StateTrace(states, events, signals, trace_hash)


def state_signal_vector(
    machine: CompiledStateMachine,
    sources: Mapping[str, Sequence[Value]],
    *,
    bar_count: int | None = None,
) -> tuple[float | None, ...]:
    """Completed-close signal, not an order instruction."""
    replay = evaluate_state_machine(machine, sources, bar_count=bar_count)
    return tuple(float(v) if v is not None else None for v in replay.signals)


def development_state_signal_vector(
    machine: CompiledStateMachine,
    market: MarketDataSet,
) -> tuple[float | None, ...]:
    """DEVELOPMENT-only single-stock daily OHLCV research boundary."""
    if (
        market.zone != DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or not market.bars
        or len(market.bars) > MAX_BARS
        or len({bar.symbol for bar in market.bars}) != 1
    ):
        raise ExpressionError("only DEVELOPMENT daily single-asset data are permitted")
    if any(a.timestamp >= b.timestamp for a, b in zip(market.bars, market.bars[1:], strict=False)):
        raise ExpressionError("market observations must be strictly ordered")
    allowed = {"open", "high", "low", "close", "volume"}
    if any(name not in allowed or kind != "number" for name, kind in machine.source_types):
        raise ExpressionError("external and unverified input sources are not permitted")
    source_values = {
        name: tuple(float(getattr(bar, name)) for bar in market.bars)
        for name, _ in machine.source_types
    }
    return state_signal_vector(machine, source_values, bar_count=len(market.bars))
