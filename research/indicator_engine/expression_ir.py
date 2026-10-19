"""P1-1: bounded, typed, causal expression trees for isolated research.

No Python/Pine evaluation, dynamic imports, network, IO, broker access,
unbounded loops or direct permission to modify the canonical StrategyIR.
A value at completed bar t uses only source values observed through t.
Use of external data requires a separately approved point-in-time adapter.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    ValidationError,
    model_validator,
)

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash

ValueType: TypeAlias = Literal["number", "boolean"]
Value: TypeAlias = float | bool | None
Operation: TypeAlias = Literal[
    "const",
    "source",
    "lag",
    "rolling_mean",
    "add",
    "sub",
    "mul",
    "div",
    "min",
    "max",
    "gt",
    "ge",
    "lt",
    "le",
    "eq",
    "and",
    "or",
    "not",
    "if_else",
    "cross_above",
    "cross_below",
]
SOURCE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_NODES = 64
MAX_DEPTH = 8
MAX_LOOKBACK = 500
MAX_BARS = 20_000
OPS: dict[str, tuple[int, ValueType, ValueType | None]] = {
    # (arity, result_type, required_operand_type) when simple.
    "add": (2, "number", "number"),
    "sub": (2, "number", "number"),
    "mul": (2, "number", "number"),
    "div": (2, "number", "number"),
    "min": (2, "number", "number"),
    "max": (2, "number", "number"),
    "gt": (2, "boolean", "number"),
    "ge": (2, "boolean", "number"),
    "lt": (2, "boolean", "number"),
    "le": (2, "boolean", "number"),
    "eq": (2, "boolean", None),
    "and": (2, "boolean", "boolean"),
    "or": (2, "boolean", "boolean"),
    "not": (1, "boolean", "boolean"),
    "cross_above": (2, "boolean", "number"),
    "cross_below": (2, "boolean", "number"),
}


class ExpressionError(ValueError):
    """An invalid or unsafe expression/observation is never executable."""


class Expression(BaseModel):
    """Recursive *data*, never source code. All unneeded properties are forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Operation
    args: tuple[Expression, ...] = ()
    value: StrictFloat | StrictBool | None = None
    name: str | None = None
    periods: int | None = Field(default=None, ge=1, le=MAX_LOOKBACK, strict=True)
    window: int | None = Field(default=None, ge=2, le=MAX_LOOKBACK, strict=True)

    @model_validator(mode="after")
    def valid_node(self) -> Expression:
        if self.op == "const":
            if (
                self.value is None
                or self.name is not None
                or self.args
                or self.periods is not None
                or self.window is not None
            ):
                raise ValueError("const requires only a finite number or boolean value")
            if type(self.value) is not bool and (
                not math.isfinite(self.value) or abs(self.value) > 1e12
            ):
                raise ValueError("nonfinite or oversized literal")
        elif self.op == "source":
            if (
                self.name is None
                or not SOURCE_NAME.fullmatch(self.name)
                or self.value is not None
                or self.args
                or self.periods is not None
                or self.window is not None
            ):
                raise ValueError("source requires only a valid declared source name")
        elif self.op == "lag":
            if (
                len(self.args) != 1
                or self.periods is None
                or self.value is not None
                or self.name is not None
                or self.window is not None
            ):
                raise ValueError("lag requires one expression and a positive past-only period")
        elif self.op == "rolling_mean":
            if (
                len(self.args) != 1
                or self.window is None
                or self.value is not None
                or self.name is not None
                or self.periods is not None
            ):
                raise ValueError("rolling_mean requires one expression and a bounded window")
        elif self.op == "if_else":
            if (
                len(self.args) != 3
                or self.value is not None
                or self.name is not None
                or self.periods is not None
                or self.window is not None
            ):
                raise ValueError("if_else requires condition, true and false expressions")
        elif self.op in OPS:
            if (
                len(self.args) != OPS[self.op][0]
                or self.value is not None
                or self.name is not None
                or self.periods is not None
                or self.window is not None
            ):
                raise ValueError("operator arity or metadata is invalid")
        else:
            raise ValueError("unreviewed operator")
        return self


Expression.model_rebuild()


@dataclass(frozen=True)
class CompiledExpression:
    expression: Expression
    source_types: tuple[tuple[str, ValueType], ...]
    result_type: ValueType
    definition_hash: str
    status: Literal["DEVELOPMENT_ONLY"] = "DEVELOPMENT_ONLY"
    broker_executable: Literal[False] = False


def compile_expression(
    expression: Expression | Mapping[str, object],
    source_types: Mapping[str, ValueType],
) -> CompiledExpression:
    """Reject implicit coercions, unavailable identifiers and costly trees."""
    try:
        raw = (
            expression.model_dump(mode="json") if isinstance(expression, Expression) else expression
        )
        expr = Expression.model_validate(raw)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ExpressionError("invalid expression schema") from exc

    if len(source_types) > 32 or not all(
        isinstance(name, str) and SOURCE_NAME.fullmatch(name) and kind in ("number", "boolean")
        for name, kind in source_types.items()
    ):
        raise ExpressionError("invalid or excessive source declarations")

    used: set[str] = set()
    count = 0

    def check(node: Expression, depth: int) -> tuple[ValueType, int]:
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ExpressionError("expression complexity budget exceeded")
        if node.op == "const":
            return ("boolean" if type(node.value) is bool else "number"), 0
        if node.op == "source":
            assert node.name is not None
            if node.name not in source_types:
                raise ExpressionError(f"source not declared: {node.name}")
            used.add(node.name)
            return source_types[node.name], 0
        children = [check(item, depth + 1) for item in node.args]
        types = [kind for kind, _ in children]
        offsets = [lag for _, lag in children]
        if node.op == "lag":
            assert node.periods is not None
            total = offsets[0] + node.periods
            result = types[0]
        elif node.op == "rolling_mean":
            assert node.window is not None
            if types[0] != "number":
                raise ExpressionError("rolling_mean needs numeric input")
            total = offsets[0] + node.window - 1
            result = "number"
        elif node.op == "if_else":
            if types[0] != "boolean" or types[1] != types[2]:
                raise ExpressionError("if_else needs boolean condition and identical branch types")
            result, total = types[1], max(offsets)
        else:
            arity, result, required = OPS[node.op]
            assert len(types) == arity
            if required is not None and any(kind != required for kind in types):
                raise ExpressionError("operator argument type mismatch")
            if node.op == "eq" and types[0] != types[1]:
                raise ExpressionError("eq arguments must share type")
            total = max(offsets) + (1 if node.op in {"cross_above", "cross_below"} else 0)
        if total > MAX_LOOKBACK:
            raise ExpressionError("cumulative lookback budget exceeded")
        return result, total

    result_type, _ = check(expr, 1)
    declared = tuple(sorted((name, source_types[name]) for name in used))
    definition_hash = content_hash(
        {
            "expression": expr.model_dump(mode="json"),
            "source_types": declared,
            "contract": "typed_expression_v1_development_only",
        }
    )
    return CompiledExpression(expr, declared, result_type, definition_hash)


def evaluate_expression(
    compiled: CompiledExpression,
    sources: Mapping[str, Sequence[Value]],
    *,
    bar_count: int | None = None,
) -> tuple[Value, ...]:
    """Return observations at completed close t; execution is not performed here."""
    replay = compile_expression(compiled.expression, dict(compiled.source_types))
    if (
        replay.definition_hash != compiled.definition_hash
        or replay.result_type != compiled.result_type
    ):
        raise ExpressionError("forged or stale compiled expression")
    names = dict(compiled.source_types)
    if set(sources) != set(names):
        raise ExpressionError("source names must match compiled declarations")
    lengths = {len(source) for source in sources.values()}
    if len(lengths) > 1:
        raise ExpressionError("source series length mismatch")
    count = lengths.pop() if lengths else bar_count
    if type(count) is not int or count < 1 or count > MAX_BARS:
        raise ExpressionError("unbounded or empty input series")
    if bar_count is not None and (type(bar_count) is not int or bar_count != count):
        raise ExpressionError("bar count does not match input series")
    checked: dict[str, tuple[Value, ...]] = {}
    for name, observations in sources.items():
        kind = names[name]
        values: list[Value] = []
        for value in observations:
            if value is None:
                values.append(None)
            elif kind == "boolean":
                if type(value) is not bool:
                    raise ExpressionError(f"source type mismatch: {name}")
                values.append(value)
            else:
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ExpressionError(f"nonfinite or invalid numeric source: {name}")
                values.append(float(value))
        checked[name] = tuple(values)

    def run(node: Expression) -> tuple[Value, ...]:
        if node.op == "source":
            assert node.name is not None
            return checked[node.name]
        if node.op == "const":
            return (node.value,) * count
        children = [run(arg) for arg in node.args]
        if node.op == "lag":
            assert node.periods is not None
            return (None,) * min(node.periods, count) + children[0][: max(0, count - node.periods)]
        if node.op == "rolling_mean":
            assert node.window is not None
            vals = children[0]
            result: list[Value] = []
            running_sum = 0.0
            missing = 0
            for t, value in enumerate(vals):
                if value is None:
                    missing += 1
                else:
                    running_sum += float(value)
                if t >= node.window:
                    old = vals[t - node.window]
                    if old is None:
                        missing -= 1
                    else:
                        running_sum -= float(old)
                if t < node.window - 1 or missing:
                    result.append(None)
                else:
                    mean = running_sum / node.window
                    result.append(mean if math.isfinite(mean) else None)
            return tuple(result)
        output: list[Value] = []
        for t in range(count):
            values = [v[t] for v in children]
            if node.op == "if_else":
                condition = values[0]
                output.append(
                    values[1] if condition is True else values[2] if condition is False else None
                )
                continue
            if node.op in {"cross_above", "cross_below"}:
                if t == 0 or any(v is None for v in values):
                    output.append(None)
                    continue
                previous = [child[t - 1] for child in children]
                if any(v is None for v in previous):
                    output.append(None)
                elif node.op == "cross_above":
                    output.append(previous[0] <= previous[1] and values[0] > values[1])  # type: ignore[operator]
                else:
                    output.append(previous[0] >= previous[1] and values[0] < values[1])  # type: ignore[operator]
                continue
            if node.op in {"and", "or"}:
                # Fail closed with missing observations; never treat None as False.
                output.append(
                    None if None in values else (all(values) if node.op == "and" else any(values))
                )
                continue
            if any(v is None for v in values):
                output.append(None)
                continue
            left = values[0]
            right = values[1] if len(values) > 1 else None
            assert left is not None
            if node.op == "not":
                item: Value = not left
            elif node.op == "add":
                item = left + right  # type: ignore[operator]
            elif node.op == "sub":
                item = left - right  # type: ignore[operator]
            elif node.op == "mul":
                item = left * right  # type: ignore[operator]
            elif node.op == "div":
                item = None if right == 0 else left / right  # type: ignore[operator]
            elif node.op == "min":
                assert right is not None
                item = min(float(left), float(right))
            elif node.op == "max":
                assert right is not None
                item = max(float(left), float(right))
            elif node.op == "gt":
                item = left > right  # type: ignore[operator]
            elif node.op == "ge":
                item = left >= right  # type: ignore[operator]
            elif node.op == "lt":
                item = left < right  # type: ignore[operator]
            elif node.op == "le":
                item = left <= right  # type: ignore[operator]
            elif node.op == "eq":
                item = left == right
            else:
                raise ExpressionError("uncompiled operator")
            if isinstance(item, (int, float)) and not math.isfinite(float(item)):
                item = None
            output.append(item)
        return tuple(output)

    return run(compiled.expression)


def signal_vector(
    compiled: CompiledExpression,
    sources: Mapping[str, Sequence[Value]],
) -> tuple[float | None, ...]:
    """Adapt an eligible boolean result to existing *research-only* signal vectors.

    Decisions are known only after t closes. Existing canonical runner must
    use the t+1 open; this function does not execute, authorize or place orders.
    """
    if compiled.result_type != "boolean":
        raise ExpressionError("entry signal must be boolean")
    return tuple(
        None if item is None else float(item) for item in evaluate_expression(compiled, sources)
    )


def development_signal_vector(
    compiled: CompiledExpression,
    market: MarketDataSet,
) -> tuple[float | None, ...]:
    """Safely produce a development-only daily single-asset OHLCV entry vector.

    This is deliberately NOT attached to the live LLM/StrategyIR registration
    path. A later version can admit PIT-verified external or derived series.
    """
    if (
        market.zone != DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or not market.bars
        or len({bar.symbol for bar in market.bars}) != 1
        or len(market.bars) > MAX_BARS
    ):
        raise ExpressionError("only bounded single-asset DEVELOPMENT daily market is allowed")
    timestamps = tuple(bar.timestamp for bar in market.bars)
    if any(a >= b for a, b in zip(timestamps, timestamps[1:], strict=False)):
        raise ExpressionError("market observations must be strictly ordered")
    allowed = {"open", "high", "low", "close", "volume"}
    if not all(name in allowed and kind == "number" for name, kind in compiled.source_types):
        raise ExpressionError("external and unverified feature inputs are not permitted")
    source_values = {
        name: tuple(float(getattr(bar, name)) for bar in market.bars)
        for name, _ in compiled.source_types
    }
    return signal_vector(compiled, source_values)
