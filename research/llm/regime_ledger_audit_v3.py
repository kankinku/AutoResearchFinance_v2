"""Independent accounting verification for V3 development regime portfolio fills.

Verifies bar-close => next-open causality and common-cash inventory, but does
not certify signal provenance, PIT data, broker execution or OOS performance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from math import isclose, isfinite

from core.costs.model import CostModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.llm.regime_portfolio_v3 import (
    ExternalNetTrade,
    RegimePortfolioResult,
    SleeveFill,
)


class RegimeLedgerError(ValueError):
    """Measured sleeve trades do not reconcile with the shared market ledger."""


@dataclass(frozen=True)
class RegimeLedgerAudit:
    audit_hash: str
    verified_fills: int
    verified_exchange_orders: int
    external_costs: float
    realized_final_equity: float
    dev_only: bool = True


def _close(a: float, b: float) -> bool:
    return isclose(a, b, rel_tol=1e-9, abs_tol=1e-7)


def audit_regime_ledger(
    result: RegimePortfolioResult,
    market: MarketDataSet,
    cost_model: CostModel,
    *,
    initial_cash: float,
) -> RegimeLedgerAudit:
    """Reconstruct cash and shares exclusively from immutable recorded fills."""
    if (
        market.zone != DataZone.DEVELOPMENT
        or result.status != "DEVELOPMENT_ONLY"
        or result.broker_executable
        or result.independent_oos_approved
        or result.data_hash != market.dataset_hash
        or len(result.cash_curve) != len(market.bars)
        or len(result.equity_curve) != len(market.bars)
        or not isfinite(initial_cash)
        or initial_cash <= 0
    ):
        raise RegimeLedgerError("invalid research-only source or aligned equity")
    filled: dict[int, list[SleeveFill]] = defaultdict(list)
    exchange: dict[int, list[ExternalNetTrade]] = defaultdict(list)
    for fill in result.sleeve_fills:
        if (
            fill.bar_index <= 0
            or fill.bar_index >= len(market.bars)
            or fill.signal_bar_index != fill.bar_index - 1
            or fill.timestamp != market.bars[fill.bar_index].timestamp.isoformat()
        ):
            raise RegimeLedgerError("next-open signal/fill timing mismatch")
        filled[fill.bar_index].append(fill)
    for trade in result.external_trades:
        if (
            trade.bar_index <= 0
            or trade.bar_index >= len(market.bars)
            or trade.timestamp != market.bars[trade.bar_index].timestamp.isoformat()
        ):
            raise RegimeLedgerError("external trade timestamp mismatch")
        exchange[trade.bar_index].append(trade)

    cash = initial_cash
    units: dict[str, float] = defaultdict(float)
    total_costs = 0.0
    for index, bar in enumerate(market.bars):
        events = filled[index]
        buys = [x for x in events if x.side == "buy"]
        sells = [x for x in events if x.side == "sell"]
        if len({x.strategy_id for x in events}) != len(events):
            raise RegimeLedgerError("duplicate sleeve fill in one bar")
        buy_gross = sum(x.gross_notional for x in buys)
        sell_gross = sum(x.gross_notional for x in sells)
        net = buy_gross - sell_gross
        orders = exchange[index]
        if abs(net) <= 1e-9 and orders:
            raise RegimeLedgerError("zero-net cash transfer charged externally")
        if abs(net) > 1e-9 and len(orders) != 1:
            raise RegimeLedgerError("missing or duplicated net external execution")
        charge = 0.0
        if orders:
            order = orders[0]
            side = "buy" if net > 0 else "sell"
            expected = cost_model.calculate(
                abs(net), side=side, stress_multiplier=1.0
            ).total
            if (
                order.side != side
                or not _close(order.gross_notional, abs(net))
                or not _close(order.cost, expected)
                or not _close(
                    order.quantity,
                    (abs(net) - expected) / bar.open if net > 0 else abs(net) / bar.open,
                )
            ):
                raise RegimeLedgerError("external net execution cost/quantity mismatch")
            charge = order.cost
        if not _close(
            charge, sum(event.allocated_external_cost for event in events)
        ):
            raise RegimeLedgerError("sleeve cost attribution does not match exchange")
        for event in sells:
            if (
                event.quantity <= 0
                or not _close(event.quantity, units[event.strategy_id])
                or not _close(event.gross_notional, event.quantity * bar.open)
                or not _close(
                    event.allocated_external_cost,
                    charge * event.gross_notional / sell_gross
                    if net < 0 else 0,
                )
            ):
                raise RegimeLedgerError("sell sleeve inventory or cost mismatch")
            units[event.strategy_id] = 0.0
        for event in buys:
            if (
                event.quantity <= 0
                or units[event.strategy_id] > 1e-9
                or not _close(
                    event.allocated_external_cost,
                    charge * event.gross_notional / buy_gross
                    if net > 0 else 0,
                )
                or not _close(
                    event.gross_notional,
                    event.quantity * bar.open + event.allocated_external_cost,
                )
            ):
                raise RegimeLedgerError("buy sleeve inventory or cost mismatch")
            units[event.strategy_id] = event.quantity

        cash += sell_gross - buy_gross - (charge if net < 0 else 0)
        total_costs += charge
        marked = cash + sum(n * bar.close for n in units.values())
        if (
            cash < -1e-7
            or not _close(cash, result.cash_curve[index])
            or not _close(marked, result.equity_curve[index])
        ):
            raise RegimeLedgerError("shared cash/equity reconciliation mismatch")
        if sum(n * bar.close for n in units.values()) > marked + 1e-7:
            raise RegimeLedgerError("leveraged or overspent shared portfolio")
    if not _close(total_costs, result.total_costs):
        raise RegimeLedgerError("aggregate transaction cost mismatch")
    expected_hash = content_hash({
        "policy_hash": result.policy_hash,
        "market_hash": market.dataset_hash,
        "equity": result.equity_curve,
        "cash": result.cash_curve,
        "sleeve_fills": [asdict(x) for x in result.sleeve_fills],
        "external_net_trades": [asdict(x) for x in result.external_trades],
        "research_only": True,
    })
    if result.trace_hash != expected_hash:
        raise RegimeLedgerError("evidence trace hash mismatch")
    proof = {
        "schema": "research-regime-shared-cash-audit-v3",
        "result_trace_hash": result.trace_hash,
        "data_hash": market.dataset_hash,
        "cost_model_hash": content_hash(asdict(cost_model)),
        "reconciled_equity": result.equity_curve,
        "reconciled_cash": result.cash_curve,
        "validated_fills": len(result.sleeve_fills),
    }
    return RegimeLedgerAudit(
        audit_hash=content_hash(proof),
        verified_fills=len(result.sleeve_fills),
        verified_exchange_orders=len(result.external_trades),
        external_costs=total_costs,
        realized_final_equity=result.equity_curve[-1],
    )
