"""P2 opt-in, costed bar-close research execution extension (development only).

New rules live OUTSIDE the immutable historical StrategyIR schema, so old
strategy hashes, G452 evidence and ordinary BacktestEngine paths stay identical.
"""

from __future__ import annotations

from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, model_validator

from strategy_ir.schema import RuleSet


class RegimeRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    when: RuleSet
    entry: RuleSet
    position_size_pct: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def require_real_signals(self) -> RegimeRoute:
        if not self.when.conditions or not self.entry.conditions:
            raise ValueError("regime and entry must contain executable conditions")
        return self


class ATRVolatilitySizing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    atr_alias: str = Field(min_length=1)
    target_atr_pct: float = Field(gt=0, le=20)
    min_position_size_pct: float = Field(gt=0, le=100)
    max_position_size_pct: float = Field(gt=0, le=100)

    @model_validator(mode="after")
    def ensure_sizing_bounds(self) -> ATRVolatilitySizing:
        if self.min_position_size_pct > self.max_position_size_pct:
            raise ValueError("invalid ATR sizing bounds")
        return self


class P2ResearchPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_version: str = "p2-research-policy-v1"
    regimes: tuple[RegimeRoute, ...] = Field(default=(), max_length=4)
    atr_sizing: ATRVolatilitySizing | None = None

    @model_validator(mode="after")
    def ensure_valid(self) -> P2ResearchPolicy:
        if self.policy_version != "p2-research-policy-v1":
            raise ValueError("unsupported P2 policy")
        if not self.regimes and self.atr_sizing is None:
            raise ValueError("empty P2 policy")
        names = [r.name for r in self.regimes]
        if len(set(names)) != len(names):
            raise ValueError("duplicate regime name")
        return self


class ChildRiskBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_child_mdd_pct: float = Field(ge=0, le=100)
    max_mdd_increase_pp: float = Field(ge=0, le=100)
    min_closed_trades: int = Field(ge=1, le=100000)


def assess_child_risk(
    *,
    parent_equity: tuple[float, ...],
    child_equity: tuple[float, ...],
    child_closed_trades: int,
    budget: ChildRiskBudget,
) -> dict[str, float | int | bool | str]:
    """Gate AFTER full-fill, all-cost backtests; never assert causality/OOS."""
    if (
        not parent_equity
        or not child_equity
        or any(not isfinite(v) or v <= 0 for v in (*parent_equity, *child_equity))
    ):
        raise ValueError("equity curves must contain positive finite observations")

    def drawdown(curve: tuple[float, ...]) -> float:
        peak = curve[0]
        result = 0.0
        for equity in curve:
            peak = max(peak, equity)
            result = max(result, 100 * (peak - equity) / peak)
        return result

    parent_dd = drawdown(parent_equity)
    child_dd = drawdown(child_equity)
    valid = (
        child_dd <= budget.max_child_mdd_pct + 1e-9
        and child_dd <= parent_dd + budget.max_mdd_increase_pp + 1e-9
        and child_closed_trades >= budget.min_closed_trades
    )
    return {
        "eligible": valid,
        "reason": "PASS" if valid else "RISK_OR_TRADE_GATE_REJECTED",
        "parent_mdd_pct": parent_dd,
        "child_mdd_pct": child_dd,
        "closed_trades": child_closed_trades,
        "max_mdd_increase_pp": budget.max_mdd_increase_pp,
    }


def assess_child_risk_metrics(
    *,
    parent_mdd_pct: float,
    child_mdd_pct: float,
    child_closed_trades: int,
    budget: ChildRiskBudget,
) -> dict[str, float | int | bool | str]:
    """Apply explicit P2 promotion budget to independently verified metrics."""
    if (
        type(child_closed_trades) is not int
        or child_closed_trades < 0
        or any(not isfinite(v) or not 0 <= v <= 100 for v in (parent_mdd_pct, child_mdd_pct))
    ):
        raise ValueError("risk promotion requires finite, valid audited metrics")
    approved = (
        child_mdd_pct <= budget.max_child_mdd_pct + 1e-9
        and child_mdd_pct <= parent_mdd_pct + budget.max_mdd_increase_pp + 1e-9
        and child_closed_trades >= budget.min_closed_trades
    )
    return {
        "eligible": approved,
        "reason": "PASS" if approved else "RISK_OR_TRADE_GATE_REJECTED",
        "parent_mdd_pct": parent_mdd_pct,
        "child_mdd_pct": child_mdd_pct,
        "closed_trades": child_closed_trades,
        "max_mdd_increase_pp": budget.max_mdd_increase_pp,
    }
