"""Fail-closed S2 audit of a genuine inherited academic StrategyIR.

The original plan decision auditor is intentionally untouched to preserve
all pre-existing evidence hashes. Canonical development engine still owns
fills, positions, costs and equity; this traces multi-rule entry/exit causally.
"""

from __future__ import annotations

from dataclasses import asdict
from math import isclose, isfinite

from core.backtest.engine import Trade, _regime_allows, _rules_match
from core.data.contracts import DataZone, MarketDataSet
from evaluation.metrics import calculate_metrics
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.decision_audit import (
    AcademicDecisionAudit,
    ClosedResearchTrade,
    DecisionAction,
    DecisionObservation,
    FillObservation,
    calculate_audit_hash,
)
from research.indicator_engine.strategy_adapter import (
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)


def audit_inherited_decisions(
    compiled: CompiledAcademicStrategy,
    market: MarketDataSet,
    *,
    initial_cash: float = 10_000.0,
) -> AcademicDecisionAudit:
    """Independently trace next-open executions for registered multi-rule IR.

    Never claim arbitrary risk modules or proprietary feature calculations are
    supported. All feature values and their cryptographic replay are checked
    through evaluate_compiled_development before interpreting decisions.
    """
    strategy = compiled.strategy
    if market.zone != DataZone.DEVELOPMENT or len({b.symbol for b in market.bars}) != 1:
        raise ResearchCatalogError("unsupported non-development or multi-symbol audit")
    if (
        not 1 <= len(strategy.entry.conditions) <= 8
        or not 1 <= len(strategy.exit.conditions) <= 8
        or len(strategy.regime_filters) > 8
        or strategy.risk.stop_loss_pct != 0
        or strategy.risk.take_profit_pct != 0
        or strategy.risk.trailing_stop_pct not in (None, 0)
        or strategy.risk.position_size_pct != 100
        or strategy.risk.daily_loss_action != "none"
        or strategy.risk.daily_loss_limit_pct is not None
        or strategy.risk.max_total_exposure_pct is not None
        or strategy.risk.max_concurrent_positions is not None
    ):
        raise ResearchCatalogError("unsupported inherited execution policy")
    signals = dict(compiled.replay.signals)
    if set(signals) != set(strategy.features) or set(signals) != set(compiled.feature_values):
        raise ResearchCatalogError("unsupported inherited indicator feature identity")
    conditions = (*strategy.entry.conditions, *strategy.exit.conditions, *strategy.regime_filters)
    for condition in conditions:
        if (
            not condition.enabled
            or condition.right is not None
            or condition.left not in signals
            or condition.op not in ("greater_than", "less_equal", "greater_equal", "less_than")
            or type(condition.value) not in (float, int)
        ):
            raise ResearchCatalogError("unsupported inherited rule operand")
    # The canonical backtester verifies compiled IR hash, dataset hash, signal
    # vector consistency, next-bar schedule and the exact fee/slippage model.
    evaluated = evaluate_compiled_development(compiled, market, initial_cash=initial_cash)
    values = {k: list(v) for k, v in signals.items()}
    fills_by_time: dict[str, tuple[int, Trade]] = {}
    for index, trade in enumerate(evaluated.trades):
        if trade.timestamp in fills_by_time:
            raise ResearchCatalogError("duplicated inherited fill timestamp")
        fills_by_time[trade.timestamp] = (index, trade)

    decisions: list[DecisionObservation] = []
    fills: list[FillObservation] = []
    closed: list[ClosedResearchTrade] = []
    open_fill: FillObservation | None = None
    held = False
    symbol = market.bars[0].symbol
    visited: set[str] = set()
    for i, bar in enumerate(market.bars):
        executed = fills_by_time.get(bar.timestamp.isoformat())
        if executed is not None:
            number, trade = executed
            visited.add(trade.timestamp)
            if (
                i == 0
                or trade.symbol != symbol
                or trade.side not in ("buy", "sell")
                or any(
                    not isfinite(x)
                    for x in (trade.price, trade.quantity, trade.notional, trade.cost)
                )
                or trade.quantity <= 0
                or trade.cost < 0
                or not isclose(trade.price, bar.open, abs_tol=1e-7)
                or not isclose(trade.notional, trade.price * trade.quantity, rel_tol=1e-9)
            ):
                raise ResearchCatalogError("unsupported inherited trade execution")
            previous = decisions[-1]
            valid = previous.earliest_execution == bar.timestamp and (
                (trade.side == "buy" and not held and previous.action == "REQUEST_ENTRY")
                or (trade.side == "sell" and held and previous.action == "REQUEST_EXIT")
            )
            if not valid:
                raise ResearchCatalogError("inherited fill has no valid close decision")
            tid = (
                f"{compiled.strategy_hash[:12]}-T-{number:06d}"
                if trade.side == "buy"
                else open_fill.trade_id
                if open_fill
                else ""
            )
            if not tid:
                raise ResearchCatalogError("orphan inherited exit fill")
            event = FillObservation(
                fill_id=f"{compiled.strategy_hash[:12]}-F-{number:06d}",
                trade_id=tid,
                decision_id=previous.decision_id,
                bar_index=i,
                execution_time=bar.timestamp,
                side=trade.side,
                price=trade.price,
                trade=trade,
            )
            if previous.fill_id != event.fill_id:
                raise ResearchCatalogError("inherited fill id does not match decision")
            fills.append(event)
            if trade.side == "buy":
                held = True
                open_fill = event
            else:
                assert open_fill is not None
                closed.append(
                    ClosedResearchTrade(
                        tid,
                        open_fill,
                        event,
                        trade.notional
                        - trade.cost
                        - open_fill.trade.notional
                        - open_fill.trade.cost,
                    )
                )
                held = False
                open_fill = None

        gate_entry = _rules_match(strategy.entry.conditions, strategy.entry.logic, values, i)
        gate_exit = _rules_match(strategy.exit.conditions, strategy.exit.logic, values, i)
        gate_regime = _regime_allows(strategy, values, i)
        incomplete = any(values[c.left][i] is None for c in conditions)
        if held:
            action: DecisionAction = "REQUEST_EXIT" if gate_exit else "HOLD_POSITION"
        elif incomplete:
            action = "WARMUP"
        elif not gate_regime:
            action = "FILTERED_REGIME"
        elif gate_entry:
            action = "REQUEST_ENTRY"
        else:
            action = "NO_ENTRY_SIGNAL"
        future = market.bars[i + 1].timestamp if i + 1 < len(market.bars) else None
        next_trade = fills_by_time.get(future.isoformat()) if future else None
        fid = f"{compiled.strategy_hash[:12]}-F-{next_trade[0]:06d}" if next_trade else None
        decisions.append(
            DecisionObservation(
                decision_id=f"{compiled.strategy_hash[:12]}-D-{i:06d}",
                symbol=symbol,
                bar_index=i,
                signal_time=bar.timestamp,
                earliest_execution=future,
                action=action,
                entry_signal=float(gate_entry),
                regime_signal=float(gate_regime),
                evaluated_gates=(
                    ("entry_positive", gate_entry),
                    ("regime_positive", gate_regime),
                    ("exit_positive", gate_exit),
                ),
                indicator_values=tuple((k, signals[k][i]) for k in sorted(signals)),
                fill_id=fid,
            )
        )
    if len(visited) != evaluated.trades_count or len(fills) != evaluated.trades_count:
        raise ResearchCatalogError("inherited canonical fills not exhausted")

    by_decision = {x.decision_id: x for x in decisions}
    losses = sorted((x for x in closed if x.net_pnl < 0), key=lambda x: x.net_pnl)[:8]
    metrics = calculate_metrics(
        evaluated.equity_curve,
        tuple(x.net_pnl for x in closed),
        periods_per_year=252.0,
        turnover=sum(f.trade.notional for f in fills) / initial_cash,
        exposure=sum(d.action in ("REQUEST_EXIT", "HOLD_POSITION") for d in decisions)
        / len(decisions),
    )
    samples = [
        {
            "fill_id": f.fill_id,
            "trade_id": f.trade_id,
            "decision_id": f.decision_id,
            "signal_time": by_decision[f.decision_id].signal_time.isoformat(),
            "execution_time": f.execution_time.isoformat(),
            "side": f.side,
            "price": f.trade.price,
            "quantity": f.trade.quantity,
            "cost": f.trade.cost,
            "indicator_values": dict(by_decision[f.decision_id].indicator_values),
            "evaluated_gates": dict(by_decision[f.decision_id].evaluated_gates),
            "decision_action": by_decision[f.decision_id].action,
        }
        for f in fills[:32]
    ]
    packet: dict[str, object] = {
        "scope": "DEVELOPMENT_INHERITED_IR_ONLY",
        "strategy_hash": compiled.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "measured_final_equity": evaluated.final_equity,
        "paid_transaction_costs": evaluated.total_paid_costs,
        "metrics": asdict(metrics),
        "execution_samples": samples,
        "more_execution_samples": max(0, len(fills) - len(samples)),
        "decision_count": len(decisions),
        "fill_count": len(fills),
        "closed_trades": len(closed),
        "losing_closed_trades": sum(x.net_pnl < 0 for x in closed),
        "loss_examples": [
            {
                "trade_id": x.trade_id,
                "net_pnl": x.net_pnl,
                "entry_decision_id": x.entry_fill.decision_id,
                "exit_decision_id": x.exit_fill.decision_id,
                "entry_indicator_values": dict(
                    by_decision[x.entry_fill.decision_id].indicator_values
                ),
                "exit_indicator_values": dict(
                    by_decision[x.exit_fill.decision_id].indicator_values
                ),
            }
            for x in losses
        ],
        "causal_claim": "NOT_ESTABLISHED",
        "hypotheses_tested": 0,
        "independent_oos": False,
        "point_in_time_verified": False,
    }
    ahash = calculate_audit_hash(evaluated, tuple(decisions), tuple(fills), tuple(closed), packet)
    packet["audit_hash"] = ahash
    return AcademicDecisionAudit(
        evaluation=evaluated,
        decisions=tuple(decisions),
        fills=tuple(fills),
        round_trips=tuple(closed),
        llm_packet=packet,
        trace_hash=ahash,
    )
