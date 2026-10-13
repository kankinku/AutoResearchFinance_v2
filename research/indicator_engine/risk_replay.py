"""Causal, cash-only, development research risk-overlay simulator.

A variance estimate is *never* directly converted to a boolean condition or
a StrategyIR static position size. It must pass an explicit fixed-budget
sizing policy. This evaluator cannot place orders or promote strategies.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from core.backtest.engine import Trade
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.bridge import prepare_development_replay
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.models import ResearchHypothesis

_COST = CostModel("academic-risk-local-v1", 1.0, 2.0, SlippageModel(5.0))
_VARIANCE_KINDS = frozenset({"parkinson_variance", "garman_klass_variance"})


@dataclass(frozen=True)
class RiskReplayPolicy:
    """Ex ante constant daily risk budget, never optimized on this dataset."""

    target_daily_variance: float = 0.0001
    max_exposure: float = 1.0
    rebalance_band: float = 0.03

    def __post_init__(self) -> None:
        if (
            not isfinite(self.target_daily_variance)
            or not 1e-8 <= self.target_daily_variance <= 0.05
        ):
            raise ValueError("target_daily_variance must be finite and in [1e-8,0.05]")
        if not isfinite(self.max_exposure) or not 0.05 <= self.max_exposure <= 1:
            raise ValueError("max_exposure must be finite, unlevered and in [0.05,1]")
        if not isfinite(self.rebalance_band) or not 0 <= self.rebalance_band <= 0.25:
            raise ValueError("rebalance_band must be finite and in [0,0.25]")


@dataclass(frozen=True)
class AcademicRiskReplayResult:
    dataset_hash: str
    hypothesis_hash: str
    replay_hash: str
    model_hash: str
    equity_hash: str
    initial_cash: float
    final_equity: float
    equity_curve: tuple[float, ...]
    fractions_at_close: tuple[float, ...]
    target_fractions_at_open: tuple[float, ...]
    trades: tuple[Trade, ...]
    trades_count: int
    total_paid_costs: float
    status: Literal["NON_PIT_DEVELOPMENT_ONLY"] = "NON_PIT_DEVELOPMENT_ONLY"
    broker_executable: Literal[False] = False
    candidate_promotable: Literal[False] = False
    benchmark_verified: Literal[False] = False
    out_of_sample_approved: Literal[False] = False


def _exposure(kind: str, reading: float | None, policy: RiskReplayPolicy) -> float:
    if reading is None or not isfinite(reading) or reading < 0:
        return 0.0
    if kind in _VARIANCE_KINDS:
        if reading <= 1e-14:
            return policy.max_exposure
        return min(policy.max_exposure, policy.target_daily_variance / reading)
    if kind == "volatility_managed_exposure":
        # The indicator already returns an ex-ante capped cash-only fraction.
        return min(policy.max_exposure, reading)
    raise ResearchCatalogError("unreviewed risk indicator cannot control exposure")


def evaluate_academic_risk_overlay(
    catalog: ResearchCatalog,
    hypothesis: ResearchHypothesis,
    dataset: MarketDataSet,
    *,
    policy: RiskReplayPolicy | None = None,
    initial_cash: float = 10_000.0,
) -> AcademicRiskReplayResult:
    """Rebalance to bar[t-1] decision at bar[t] open, applying all trade costs."""
    policy = policy if policy is not None else RiskReplayPolicy()
    if DataZone(dataset.zone) is not DataZone.DEVELOPMENT:
        raise ResearchCatalogError("non-development data cannot enter research risk replay")
    if len(hypothesis.roles) != 3 or hypothesis.roles != ("entry", "regime", "risk"):
        raise ResearchCatalogError("explicit entry/regime/risk roles are required")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("initial_cash must be finite and positive")
    # Includes verification, composition identity, OHLC sanity, and sealed-zone check.
    replay = prepare_development_replay(catalog, hypothesis, dataset)
    names = hypothesis.signal_ids
    kinds = tuple(catalog.get_indicator(name).calculator for name in names)
    if kinds[0] not in {"time_series_momentum", "previous_range_breakout"}:
        raise ResearchCatalogError("unreviewed entry calculator")
    if kinds[1] != "sma_direction":
        raise ResearchCatalogError("unreviewed regime calculator")
    if kinds[2] not in _VARIANCE_KINDS | {"volatility_managed_exposure"}:
        raise ResearchCatalogError("unreviewed risk indicator")
    if kinds[2] == "volatility_managed_exposure":
        predefined = catalog.get_indicator(names[2]).target_daily_variance
        if predefined != policy.target_daily_variance:
            raise ResearchCatalogError(
                "risk target already fixed in academic indicator; conflicting policy"
            )
    values = dict(replay.signals)
    cash = initial_cash
    units = 0.0
    trades: list[Trade] = []
    equity_curve: list[float] = []
    fractions: list[float] = []
    target_fractions: list[float] = []
    # For linear costs, compute exact upfront cap on acquisition cash.
    cost_rate = _COST.calculate(1.0, side="buy", stress_multiplier=1.0).total
    for index, bar in enumerate(dataset.bars):
        equity_open = cash + units * bar.open
        if not isfinite(equity_open) or equity_open <= 0:
            raise ResearchCatalogError("invalid open equity")
        fraction = 0.0
        if index:
            entry = values[names[0]][index - 1]
            regime = values[names[1]][index - 1]
            risk = values[names[2]][index - 1]
            if entry is not None and entry > 0.5:
                # Regime is an entry gate, not a forced exit if already invested.
                if units > 0 or (regime is not None and regime > 0.5):
                    fraction = _exposure(kinds[2], risk, policy)
        if not isfinite(fraction) or not 0 <= fraction <= policy.max_exposure:
            raise ResearchCatalogError("invalid causal exposure")
        target_fractions.append(fraction)
        target_notional = equity_open * fraction
        held_notional = units * bar.open
        mismatch = target_notional - held_notional
        # Always close a position upon a real exit or invalid risk measurement.
        should_trade = (
            (fraction == 0 and units > 0)
            or abs(mismatch) > max(1e-9, policy.rebalance_band * equity_open)
        )
        if should_trade and mismatch < 0:
            sell_notional = min(held_notional, -mismatch)
            quantity = sell_notional / bar.open
            paid = _COST.calculate(sell_notional, side="sell", stress_multiplier=1.0).total
            cash += sell_notional - paid
            units -= quantity
            if units < 1e-12:
                units = 0.0
            trades.append(
                Trade(bar.timestamp.isoformat(), "sell", bar.open, quantity,
                      sell_notional, paid, bar.symbol)
            )
        elif should_trade and mismatch > 0:
            # Buy cost must fit inside available cash; never borrow or leverage.
            buy_notional = min(mismatch, max(0.0, cash) / (1 + cost_rate))
            if buy_notional > 1e-9:
                quantity = buy_notional / bar.open
                paid = _COST.calculate(buy_notional, side="buy", stress_multiplier=1.0).total
                cash -= buy_notional + paid
                units += quantity
                if cash < 0 and cash > -1e-8:
                    cash = 0.0
                if cash < -1e-8:
                    raise ResearchCatalogError("unfunded risk trade")
                trades.append(
                    Trade(bar.timestamp.isoformat(), "buy", bar.open, quantity,
                          buy_notional, paid, bar.symbol)
                )
        equity_close = cash + units * bar.close
        if not isfinite(equity_close) or equity_close <= 0:
            raise ResearchCatalogError("invalid marked equity")
        fraction_close = units * bar.close / equity_close
        if not -1e-12 <= fraction_close <= 1 + 1e-10:
            raise ResearchCatalogError("margin or short sale detected")
        equity_curve.append(equity_close)
        fractions.append(max(0.0, fraction_close))
    identity = {
        "hypothesis": hypothesis.identity_hash,
        "data": dataset.dataset_hash,
        "replay": replay.replay_hash,
        "policy": policy.__dict__,
        "cost": _COST.version,
        "adapter_version": 1,
    }
    return AcademicRiskReplayResult(
        dataset_hash=dataset.dataset_hash,
        hypothesis_hash=hypothesis.identity_hash,
        replay_hash=replay.replay_hash,
        model_hash=content_hash(identity),
        equity_hash=content_hash(tuple(equity_curve)),
        initial_cash=initial_cash,
        final_equity=equity_curve[-1],
        equity_curve=tuple(equity_curve),
        fractions_at_close=tuple(fractions),
        target_fractions_at_open=tuple(target_fractions),
        trades=tuple(trades),
        trades_count=len(trades),
        total_paid_costs=sum(t.cost for t in trades),
    )
