"""Research-only bridge and independent accounting audit for dynamic risk overlays.

Canonical StrategyIR currently supports static position_size_pct, not per-bar
exposure. Preserve its approved entry/exit representation, bind a separate
immutable risk instruction, and REFUSE native order/promotion paths.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isclose, isfinite
from typing import Literal

from core.backtest.engine import Trade
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.bridge import prepare_development_replay
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.models import ResearchHypothesis
from research.indicator_engine.risk_replay import (
    AcademicRiskReplayResult,
    RiskReplayPolicy,
    evaluate_academic_risk_overlay,
)
from research.indicator_engine.strategy_adapter import (
    CompiledAcademicStrategy,
    compile_research_hypothesis,
)

_AUDIT_COST = CostModel("academic-risk-local-v1", 1.0, 2.0, SlippageModel(5.0))
_RISK_KINDS = frozenset({
    "garman_klass_variance", "parkinson_variance", "volatility_managed_exposure"
})


@dataclass(frozen=True)
class CompiledAcademicRiskPlan:
    hypothesis: ResearchHypothesis
    base: CompiledAcademicStrategy
    policy: RiskReplayPolicy
    dataset_hash: str
    risk_signal_id: str
    risk_definition_hash: str
    risk_replay_hash: str
    plan_hash: str
    status: Literal["RESEARCH_RISK_ONLY"] = "RESEARCH_RISK_ONLY"
    broker_executable: Literal[False] = False
    candidate_promotable: Literal[False] = False
    sealed_oos_approved: Literal[False] = False


@dataclass(frozen=True)
class RiskAccountingAudit:
    verified_bars: int
    verified_trades: int
    max_equity_error: float
    max_exposure_error: float
    audit_hash: str
    status: Literal["DEVELOPMENT_LEDGER_VERIFIED"] = "DEVELOPMENT_LEDGER_VERIFIED"
    broker_executable: Literal[False] = False


def compile_academic_risk_plan(
    catalog: ResearchCatalog,
    hypothesis: ResearchHypothesis,
    dataset: MarketDataSet,
    *,
    policy: RiskReplayPolicy | None = None,
) -> CompiledAcademicRiskPlan:
    """Compile canonical binary StrategyIR + guarded NON-NATIVE dynamic risk sidecar."""
    policy = policy if policy is not None else RiskReplayPolicy()
    if hypothesis.roles != ("entry", "regime", "risk"):
        raise ResearchCatalogError("only explicit entry/regime/risk research roles allowed")
    replay = prepare_development_replay(catalog, hypothesis, dataset)
    risk_signal_id = hypothesis.signal_ids[2]
    signal = catalog.get_indicator(risk_signal_id)
    if signal.calculator not in _RISK_KINDS:
        raise ResearchCatalogError("unreviewed risk exposure semantics")
    if (
        signal.calculator == "volatility_managed_exposure"
        and signal.target_daily_variance != policy.target_daily_variance
    ):
        raise ResearchCatalogError("risk target already fixed in indicator; inconsistent policy")
    base_hypotheses = compose_hypotheses(catalog, signal_ids=hypothesis.signal_ids[:2])
    if len(base_hypotheses) != 1:
        raise ResearchCatalogError("cannot bind unique native entry/exit strategy")
    base = compile_research_hypothesis(catalog, base_hypotheses[0], dataset)
    risk_definition_hash = content_hash(signal.model_dump(mode="json"))
    plan_hash = content_hash({
        "version": 1,
        "full_hypothesis": hypothesis.identity_hash,
        "data": dataset.dataset_hash,
        "base_strategy": base.strategy_hash,
        "base_replay": base.replay.replay_hash,
        "risk_signal": risk_signal_id,
        "risk_definition": risk_definition_hash,
        "risk_replay": replay.replay_hash,
        "policy": policy.__dict__,
        "cost": _AUDIT_COST.version,
        "runtime": "research-only-dynamic-cash-v1",
    })
    return CompiledAcademicRiskPlan(
        hypothesis=hypothesis, base=base, policy=policy,
        dataset_hash=dataset.dataset_hash, risk_signal_id=risk_signal_id,
        risk_definition_hash=risk_definition_hash,
        risk_replay_hash=replay.replay_hash, plan_hash=plan_hash,
    )


def _match(actual: float, expected: float, field: str) -> float:
    if not isfinite(actual) or not isfinite(expected):
        raise ResearchCatalogError(f"risk accounting audit non-finite {field}")
    delta = abs(actual - expected)
    if not isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8):
        raise ResearchCatalogError(f"risk accounting audit mismatched {field}")
    return delta


def verify_risk_accounting(
    result: AcademicRiskReplayResult,
    dataset: MarketDataSet,
    *,
    policy: RiskReplayPolicy,
) -> RiskAccountingAudit:
    """Independent ledger: recompute costs, cash, lots, mark-to-market and band.

    Audit does not claim that a risk signal was PIT-valid or that a static
    StrategyIR engine performed a dynamic rebalance. Those are separate gates.
    """
    bars = dataset.bars
    n = len(bars)
    if (
        dataset.zone != DataZone.DEVELOPMENT
        or result.dataset_hash != dataset.dataset_hash
        or n != len(result.equity_curve)
        or n != len(result.target_fractions_at_open)
        or n != len(result.fractions_at_close)
        or result.trades_count != len(result.trades)
        or not isfinite(result.initial_cash)
        or result.initial_cash <= 0
    ):
        raise ResearchCatalogError("risk accounting audit invalid result boundary")
    if not bars:
        raise ResearchCatalogError("risk accounting audit empty data")
    by_time = {bar.timestamp.isoformat(): (i, bar) for i, bar in enumerate(bars)}
    trade_by_index: dict[int, Trade] = {}
    for trade in result.trades:
        row = by_time.get(trade.timestamp)
        if row is None or row[0] == 0 or row[0] in trade_by_index:
            raise ResearchCatalogError("risk accounting audit wrong trade timestamp")
        trade_by_index[row[0]] = trade
    cash = result.initial_cash
    units = 0.0
    error_equity = 0.0
    error_exposure = 0.0
    paid_cost = 0.0
    for i, bar in enumerate(bars):
        requested = result.target_fractions_at_open[i]
        if not isfinite(requested) or not 0 <= requested <= policy.max_exposure:
            raise ResearchCatalogError("risk accounting audit invalid target exposure")
        if i == 0 and requested != 0:
            raise ResearchCatalogError("risk accounting audit used same-bar signals")
        opened = cash + units * bar.open
        if not isfinite(opened) or opened <= 0:
            raise ResearchCatalogError("risk accounting audit invalid opening equity")
        mismatch = opened * requested - units * bar.open
        should_trade = (
            (requested == 0 and units > 0)
            or abs(mismatch) > max(1e-9, policy.rebalance_band * opened)
        )
        active_trade = trade_by_index.get(i)
        expected_notional = 0.0
        if should_trade:
            if mismatch < 0:
                expected_notional = min(units * bar.open, -mismatch)
            elif mismatch > 0:
                rate = _AUDIT_COST.calculate(1.0, side="buy", stress_multiplier=1.0).total
                expected_notional = min(mismatch, max(0.0, cash) / (1 + rate))
        if active_trade is None:
            if expected_notional > 1e-8:
                raise ResearchCatalogError("risk accounting audit missed rebalance")
        else:
            if expected_notional <= 1e-9:
                raise ResearchCatalogError("risk accounting audit unexpected trade")
            side = "buy" if mismatch > 0 else "sell"
            if active_trade.side != side or active_trade.symbol != bar.symbol:
                raise ResearchCatalogError("risk accounting audit invalid trade direction")
            _match(active_trade.price, bar.open, "open fill")
            _match(active_trade.notional, expected_notional, "notional")
            _match(active_trade.quantity, expected_notional / bar.open, "quantity")
            cost = _AUDIT_COST.calculate(expected_notional, side=side, stress_multiplier=1.0).total
            _match(active_trade.cost, cost, "cost")
            paid_cost += cost
            if side == "buy":
                units += active_trade.quantity
                cash -= expected_notional + cost
            else:
                units -= active_trade.quantity
                cash += expected_notional - cost
                if units < 1e-12:
                    units = 0.0
        if cash < -1e-8 or units < -1e-12:
            raise ResearchCatalogError("risk accounting audit detected leverage/short")
        marked = cash + units * bar.close
        if marked <= 0 or not isfinite(marked):
            raise ResearchCatalogError("risk accounting audit invalid close equity")
        error_equity = max(error_equity, _match(result.equity_curve[i], marked, "equity"))
        fraction = units * bar.close / marked
        error_exposure = max(error_exposure, _match(result.fractions_at_close[i], fraction,
                                                    "marked exposure"))
    _match(result.final_equity, result.equity_curve[-1], "final equity")
    _match(result.total_paid_costs, paid_cost, "total fees")
    if result.equity_hash != content_hash(result.equity_curve):
        raise ResearchCatalogError("risk accounting audit equity fingerprint mismatch")
    return RiskAccountingAudit(
        verified_bars=n, verified_trades=len(result.trades),
        max_equity_error=error_equity, max_exposure_error=error_exposure,
        audit_hash=content_hash({
            "dataset": result.dataset_hash,
            "model": result.model_hash,
            "curve": result.equity_hash,
            "trades": [asdict(trade) for trade in result.trades],
            "policy": policy.__dict__,
            "cost": _AUDIT_COST.version,
            "audit": "independent-ledger-v1",
        }),
    )


def evaluate_compiled_risk_development(
    catalog: ResearchCatalog,
    plan: CompiledAcademicRiskPlan,
    dataset: MarketDataSet,
    *,
    initial_cash: float = 10_000.0,
) -> AcademicRiskReplayResult:
    """Guarded research sidecar: no native dynamic StrategyIR or broker action."""
    if dataset.dataset_hash != plan.dataset_hash:
        raise ResearchCatalogError("risk plan dataset hash mismatch")
    expected = compile_academic_risk_plan(
        catalog, plan.hypothesis, dataset, policy=plan.policy
    )
    if expected != plan:
        raise ResearchCatalogError("risk plan/StrategyIR integrity mismatch")
    result = evaluate_academic_risk_overlay(
        catalog, plan.hypothesis, dataset, policy=plan.policy, initial_cash=initial_cash,
    )
    verify_risk_accounting(result, dataset, policy=plan.policy)
    return result
