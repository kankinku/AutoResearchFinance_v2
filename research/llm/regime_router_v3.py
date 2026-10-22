"""V3 typed regime router — signal selection only, no orders or backtest.

Independent per-route exits, position lifecycles and shared portfolio accounting
must be implemented and audited before this can count as a multi-strategy engine.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.backtest.engine import _rules_match
from strategy_ir.schema import RuleSet


class RegimeRouteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    when: RuleSet
    strategy_id: str = Field(min_length=1)
    allocation_pct: float = Field(gt=0, le=100)

    @model_validator(mode="after")
    def require_conditions(self) -> RegimeRouteSpec:
        if not self.when.conditions:
            raise ValueError("regime route needs at least one condition")
        if any(not condition.enabled for condition in self.when.conditions):
            raise ValueError("disabled route conditions are not supported")
        return self


class RegimeRouterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["exclusive", "weighted"]
    routes: tuple[RegimeRouteSpec, ...] = Field(min_length=1, max_length=4)
    unknown_policy: Literal["cash"] = "cash"
    transition_policy: Literal["hold_previous_until_exit", "flatten_on_switch"] = (
        "hold_previous_until_exit"
    )

    @model_validator(mode="after")
    def check_routes(self) -> RegimeRouterSpec:
        names = [route.name for route in self.routes]
        if len(names) != len(set(names)):
            raise ValueError("duplicate regime route")
        if self.mode == "weighted" and sum(r.allocation_pct for r in self.routes) > 100:
            raise ValueError("total route allocation exceeds 100 percent")
        return self


@dataclass(frozen=True)
class SelectedRegime:
    name: str
    strategy_id: str
    allocation_pct: float


def resolve_regime_routes(
    program: RegimeRouterSpec,
    values: Mapping[str, Sequence[float | None]],
    completed_bar_index: int,
) -> tuple[SelectedRegime, ...]:
    """Deterministic selection based on *completed* bar data; no fills occur.

    The execution adapter must later trade no earlier than the next open.
    In exclusive mode the first matching route wins; unknown => stay in cash.
    """
    if type(completed_bar_index) is not int or completed_bar_index < 0:
        raise ValueError("invalid completed bar index")
    needed = {
        alias
        for route in program.routes
        for condition in route.when.conditions
        for alias in (condition.left, condition.right)
        if alias is not None
    }
    for alias in needed:
        if alias not in values or completed_bar_index >= len(values[alias]):
            raise ValueError(f"missing aligned regime signal: {alias}")
    frame = {k: list(v) for k, v in values.items()}
    selected: list[SelectedRegime] = []
    for route in program.routes:
        if _rules_match(
            route.when.conditions, route.when.logic, frame, completed_bar_index
        ):
            selected.append(SelectedRegime(
                route.name, route.strategy_id, route.allocation_pct,
            ))
            if program.mode == "exclusive":
                break
    return tuple(selected)
