"""Development-only causal *observation* trace for reviewed academic strategies.

The canonical engine remains the sole source of fills and PnL. This read-only
adapter links each recorded execution to a signal on the preceding completed
bar, rather than asking an LLM to invent a reason for a historical fill.
It supports the deliberately restricted two-binary-signal academic adapter;
it does NOT claim to reproduce arbitrary StrategyIR blocking/risk decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import isclose, isfinite
from typing import Literal

from core.backtest.engine import Trade
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.strategy_adapter import (
    AcademicDevelopmentResult,
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)

DecisionAction = Literal[
    "WARMUP", "REQUEST_ENTRY", "REQUEST_EXIT", "HOLD_POSITION",
    "FILTERED_REGIME", "NO_ENTRY_SIGNAL",
]


@dataclass(frozen=True)
class DecisionObservation:
    decision_id: str
    symbol: str
    bar_index: int
    signal_time: datetime
    earliest_execution: datetime | None
    action: DecisionAction
    entry_signal: float | None
    regime_signal: float | None
    evaluated_gates: tuple[tuple[str, bool | None], ...]
    indicator_values: tuple[tuple[str, float | None], ...]
    fill_id: str | None


@dataclass(frozen=True)
class FillObservation:
    fill_id: str
    trade_id: str
    decision_id: str
    bar_index: int
    execution_time: datetime
    side: str
    price: float
    trade: Trade


@dataclass(frozen=True)
class ClosedResearchTrade:
    trade_id: str
    entry_fill: FillObservation
    exit_fill: FillObservation
    net_pnl: float


@dataclass(frozen=True)
class AcademicDecisionAudit:
    evaluation: AcademicDevelopmentResult
    decisions: tuple[DecisionObservation, ...]
    fills: tuple[FillObservation, ...]
    round_trips: tuple[ClosedResearchTrade, ...]
    llm_packet: dict[str, object]
    trace_hash: str
    status: Literal["RESEARCH_DECISION_AUDIT_ONLY"] = "RESEARCH_DECISION_AUDIT_ONLY"
    candidate_promotable: Literal[False] = False
    point_in_time_verified: Literal[False] = False
    broker_executable: Literal[False] = False


def _signal_value(x: float | None) -> bool | None:
    return None if x is None else x > 0.5


def calculate_audit_hash(
    evaluation: AcademicDevelopmentResult,
    decisions: tuple[DecisionObservation, ...],
    fills: tuple[FillObservation, ...],
    round_trips: tuple[ClosedResearchTrade, ...],
    packet: dict[str, object],
) -> str:
    """Bind *all* causal inputs, actual fills, computed metrics and LLM packet.

    Excludes only the self-referential `audit_hash` entry. The result is a
    research checksum, not a cryptographic signature of an external vendor.
    """
    return content_hash({
        "schema": "research-decision-audit-evidence-v2",
        "evaluation": {
            "strategy": evaluation.strategy_hash,
            "dataset": evaluation.dataset_hash,
            "replay": evaluation.replay_hash,
            "equity_hash": evaluation.equity_hash,
            "equity_curve": evaluation.equity_curve,
            # Trade consists exclusively of immutable JSON primitives.
            # dataclasses.asdict recursively deep-copies these thousands of
            # times during inherited S2/S7 lineage replay; a shallow snapshot
            # has identical canonical bytes without the copy overhead.
            "trades": [vars(t).copy() for t in evaluation.trades],
            "initial_cash": evaluation.initial_cash,
            "final_equity": evaluation.final_equity,
            "paid_costs": evaluation.total_paid_costs,
        },
        # Tuples of scalars are JSON lists in canonical_bytes, just as the
        # nested asdict representation was. Keep the existing v2 audit schema
        # and every field/ISO timestamp byte-for-byte compatible.
        "decisions": [
            {
                **vars(d),
                "signal_time": d.signal_time.isoformat(),
                "earliest_execution": (
                    d.earliest_execution.isoformat() if d.earliest_execution else None
                ),
            }
            for d in decisions
        ],
        "fills": [
            {
                **vars(f),
                "execution_time": f.execution_time.isoformat(),
                "trade": vars(f.trade).copy(),
            }
            for f in fills
        ],
        "round_trips": [
            (t.trade_id, t.entry_fill.fill_id, t.exit_fill.fill_id, t.net_pnl)
            for t in round_trips
        ],
        "analysis_packet": {k: v for k, v in packet.items() if k != "audit_hash"},
    })


def audit_compiled_academic_decisions(
    compiled: CompiledAcademicStrategy,
    market: MarketDataSet,
    *,
    initial_cash: float = 10_000.0,
) -> AcademicDecisionAudit:
    """Replay one *existing* reviewed academic strategy and build evidence.

    Supports only the narrow approved academic compiler's long-only,
    zero-risk-stop, two-boolean-signal policy. Every observed fill must match
    the immediately previous close decision; otherwise fail closed. These
    are observable decision-rule evaluations, NOT verified economic causes.
    """
    if market.zone != DataZone.DEVELOPMENT:
        raise ResearchCatalogError("only development data may enter decision audit")
    strategy = compiled.strategy
    if (
        len(strategy.entry.conditions) != 1
        or len(strategy.exit.conditions) != 1
        or len(strategy.regime_filters) != 1
        or strategy.entry.logic != "AND"
        or strategy.exit.logic != "OR"
        or strategy.entry.conditions[0].op != "greater_than"
        or strategy.exit.conditions[0].op != "less_equal"
        or strategy.regime_filters[0].op != "greater_than"
        or strategy.risk.stop_loss_pct != 0
        or strategy.risk.take_profit_pct != 0
        or strategy.risk.trailing_stop_pct not in (None, 0)
        or strategy.risk.position_size_pct != 100
        or strategy.risk.daily_loss_action != "none"
        or strategy.risk.max_total_exposure_pct is not None
        or strategy.risk.daily_loss_limit_pct is not None
        or strategy.risk.max_concurrent_positions is not None
        or any(x.enabled is not True for x in (
            strategy.entry.conditions[0], strategy.exit.conditions[0],
            strategy.regime_filters[0],
        ))
        or any(x.value != 0.5 for x in (
            strategy.entry.conditions[0], strategy.exit.conditions[0],
            strategy.regime_filters[0],
        ))
    ):
        raise ResearchCatalogError("unsupported execution policy in reviewed academic audit")
    entry_key = strategy.entry.conditions[0].left
    exit_key = strategy.exit.conditions[0].left
    regime_key = strategy.regime_filters[0].left
    if entry_key != exit_key or entry_key == regime_key:
        raise ResearchCatalogError("academic entry/exit/regime mismatch")
    names = tuple(name for name, _ in compiled.replay.signals)
    if len(names) < 2 or not {entry_key, regime_key}.issubset(names):
        raise ResearchCatalogError("academic replay roles mismatch")
    if len(set(names)) != len(names) or set(names) != set(strategy.features):
        raise ResearchCatalogError("replay indicators do not match strategy feature contract")
    # This validation invokes the actual canonical engine once, including all
    # previously approved SHA checks and the immutable real fill/cost result.
    evaluated = evaluate_compiled_development(compiled, market, initial_cash=initial_cash)
    signals = dict(compiled.replay.signals)
    entry_values, regime_values = signals[entry_key], signals[regime_key]
    if len(entry_values) != len(market.bars) or len(regime_values) != len(market.bars):
        raise ResearchCatalogError("invalid replay vector width")
    by_bar: dict[str, tuple[int, Trade]] = {}
    for trade_idx, trade in enumerate(evaluated.trades):
        if trade.timestamp in by_bar:
            raise ResearchCatalogError("multiple fills on one academic bar unsupported")
        by_bar[trade.timestamp] = (trade_idx, trade)
    decisions: list[DecisionObservation] = []
    fills: list[FillObservation] = []
    closed: list[ClosedResearchTrade] = []
    open_fill: FillObservation | None = None
    position_open = False
    observed = set()
    symbol = market.bars[0].symbol
    if len({bar.symbol for bar in market.bars}) != 1:
        raise ResearchCatalogError("decision audit requires single symbol")

    for i, bar in enumerate(market.bars):
        current = by_bar.get(bar.timestamp.isoformat())
        if current is not None:
            number, trade = current
            observed.add(trade.timestamp)
            if i == 0 or trade.symbol != symbol or trade.side not in ("buy", "sell"):
                raise ResearchCatalogError("invalid fill without prior decision")
            if (
                not all(isfinite(x) for x in (
                    trade.price, trade.quantity, trade.notional, trade.cost
                ))
                or trade.quantity <= 0 or trade.cost < 0
                or not isclose(trade.price, bar.open, abs_tol=1e-7)
                or not isclose(trade.notional, trade.price * trade.quantity, rel_tol=1e-9)
            ):
                raise ResearchCatalogError("fill integrity or next-open price mismatch")
            parent = decisions[-1]
            if (parent.earliest_execution != bar.timestamp or
                ((trade.side == "buy" and (position_open or parent.action != "REQUEST_ENTRY"))
                 or (trade.side == "sell" and (
                     not position_open or parent.action != "REQUEST_EXIT"
                 )))):
                raise ResearchCatalogError("execution cannot be linked to valid close signal")
            trade_id = (
                f"{compiled.strategy_hash[:12]}-T-{number:06d}"
                if trade.side == "buy" else open_fill.trade_id if open_fill else ""
            )
            if not trade_id:
                raise ResearchCatalogError("exit has no matched research entry")
            event = FillObservation(
                fill_id=f"{compiled.strategy_hash[:12]}-F-{number:06d}",
                trade_id=trade_id, decision_id=parent.decision_id,
                bar_index=i, execution_time=bar.timestamp, side=trade.side,
                price=trade.price, trade=trade,
            )
            if parent.fill_id != event.fill_id:
                raise ResearchCatalogError("fill id and decision link mismatch")
            fills.append(event)
            if trade.side == "buy":
                position_open = True
                open_fill = event
            else:
                assert open_fill is not None
                closed.append(ClosedResearchTrade(
                    trade_id, open_fill, event,
                    trade.notional - trade.cost
                    - open_fill.trade.notional - open_fill.trade.cost,
                ))
                position_open = False
                open_fill = None

        entry = entry_values[i]
        regime = regime_values[i]
        if entry is None or regime is None:
            action: DecisionAction = "HOLD_POSITION" if position_open else "WARMUP"
        elif position_open:
            action = "REQUEST_EXIT" if not _signal_value(entry) else "HOLD_POSITION"
        elif not _signal_value(regime):
            action = "FILTERED_REGIME"
        elif _signal_value(entry):
            action = "REQUEST_ENTRY"
        else:
            action = "NO_ENTRY_SIGNAL"
        future = market.bars[i + 1].timestamp if i + 1 < len(market.bars) else None
        subsequent = by_bar.get(future.isoformat()) if future is not None else None
        fill_id = (
            f"{compiled.strategy_hash[:12]}-F-{subsequent[0]:06d}"
            if subsequent is not None else None
        )
        snapshot = tuple((name, signals[name][i]) for name in sorted(signals))
        decisions.append(DecisionObservation(
            decision_id=f"{compiled.strategy_hash[:12]}-D-{i:06d}",
            symbol=symbol, bar_index=i, signal_time=bar.timestamp,
            earliest_execution=future, action=action,
            entry_signal=entry, regime_signal=regime,
            evaluated_gates=(("entry_positive", _signal_value(entry)),
                             ("regime_positive", _signal_value(regime))),
            indicator_values=snapshot, fill_id=fill_id,
        ))
    if len(observed) != len(evaluated.trades) or len(fills) != len(evaluated.trades):
        raise ResearchCatalogError("unmatched canonical fills")

    # Deterministic bounded LLM *context*, NOT an LLM causal explanation.
    losses = sorted((x for x in closed if x.net_pnl < 0), key=lambda x: x.net_pnl)[:8]
    by_decision = {x.decision_id: x for x in decisions}
    exposure_days = sum(x.action in ("HOLD_POSITION", "REQUEST_EXIT") for x in decisions)
    metrics = calculate_metrics(
        evaluated.equity_curve, tuple(t.net_pnl for t in closed),
        periods_per_year=252.0,
        turnover=sum(f.trade.notional for f in fills) / initial_cash,
        exposure=exposure_days / len(decisions),
    )
    fill_samples = [
        {
            "fill_id": f.fill_id, "trade_id": f.trade_id,
            "decision_id": f.decision_id,
            "signal_time": by_decision[f.decision_id].signal_time.isoformat(),
            "execution_time": f.execution_time.isoformat(),
            "side": f.side, "price": f.trade.price,
            "quantity": f.trade.quantity, "cost": f.trade.cost,
            "indicator_values": dict(by_decision[f.decision_id].indicator_values),
            "evaluated_gates": dict(by_decision[f.decision_id].evaluated_gates),
            "decision_action": by_decision[f.decision_id].action,
        }
        for f in fills[:32]
    ]
    packet: dict[str, object] = {
        "scope": "DEVELOPMENT_REVIEWED_ACADEMIC_ONLY",
        "strategy_hash": compiled.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "measured_final_equity": evaluated.final_equity,
        "paid_transaction_costs": evaluated.total_paid_costs,
        "metrics": asdict(metrics),
        "execution_samples": fill_samples,
        "more_execution_samples": max(0, len(fills) - len(fill_samples)),
        "decision_count": len(decisions),
        "fill_count": len(fills),
        "closed_trades": len(closed),
        "losing_closed_trades": sum(x.net_pnl < 0 for x in closed),
        "loss_examples": [
            {"trade_id": x.trade_id, "net_pnl": x.net_pnl,
             "entry_decision_id": x.entry_fill.decision_id,
             "exit_decision_id": x.exit_fill.decision_id,
             "entry_indicator_values": dict(
                 by_decision[x.entry_fill.decision_id].indicator_values
             ),
             "exit_indicator_values": dict(
                 by_decision[x.exit_fill.decision_id].indicator_values
             )}
            for x in losses
        ],
        "causal_claim": "NOT_ESTABLISHED",
        "hypotheses_tested": 0,
        "independent_oos": False,
        "point_in_time_verified": False,
    }
    audit_hash = calculate_audit_hash(
        evaluated, tuple(decisions), tuple(fills), tuple(closed), packet,
    )
    packet["audit_hash"] = audit_hash
    return AcademicDecisionAudit(
        evaluation=evaluated, decisions=tuple(decisions), fills=tuple(fills),
        round_trips=tuple(closed), llm_packet=packet, trace_hash=audit_hash,
    )
