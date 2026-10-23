"""Development-only single-symbol regime portfolio with shared cash.

Opt-in V3 research adapter. Independent rule signals schedule next-open
fills; same-symbol sleeves share one cash account, and opposite same-open
sleeve changes are internally netted with costs paid only on the *external*
net order. It is NOT production broker, S2-certified composite promotion,
point-in-time validation or a multi-asset execution simulator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from math import isfinite

from core.backtest.engine import _regime_allows, _risk_exit, _rules_match
from core.costs.model import CostModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.llm.regime_router_v3 import RegimeRouterSpec, resolve_regime_routes
from strategy_ir.schema import Condition, StrategyIR


class RegimePortfolioError(ValueError):
    """The V3 experimental portfolio is not independently executable."""


@dataclass(frozen=True)
class SleeveFill:
    strategy_id: str
    side: str
    bar_index: int
    signal_bar_index: int
    timestamp: str
    quantity: float
    gross_notional: float
    allocated_external_cost: float


@dataclass(frozen=True)
class ExternalNetTrade:
    side: str
    bar_index: int
    timestamp: str
    gross_notional: float
    quantity: float
    cost: float


@dataclass(frozen=True)
class RegimePortfolioResult:
    data_hash: str
    policy_hash: str
    equity_curve: tuple[float, ...]
    cash_curve: tuple[float, ...]
    sleeve_fills: tuple[SleeveFill, ...]
    external_trades: tuple[ExternalNetTrade, ...]
    total_costs: float
    trace_hash: str
    status: str = "DEVELOPMENT_ONLY"
    broker_executable: bool = False
    independent_oos_approved: bool = False


@dataclass
class _Sleeve:
    units: float = 0.0
    entry_price: float = 0.0
    peak_close: float = 0.0
    pending_exit: int | None = None
    pending_entry: tuple[int, float] | None = None


def _require_operand(condition: Condition, values: Mapping[str, list[float | None]]) -> None:
    if not condition.enabled:
        raise RegimePortfolioError("disabled regime/strategy condition unsupported")
    if condition.left not in values or (
        condition.right is not None and condition.right not in values
    ):
        raise RegimePortfolioError("missing aligned signal in regime/strategy condition")
    if condition.op in ("cross_above", "cross_below"):
        if condition.right is None or condition.value is not None:
            raise RegimePortfolioError("cross requires a right series without scalar")
    elif (condition.right is None) == (condition.value is None):
        raise RegimePortfolioError("comparison requires exactly one right or value")
    threshold = condition.value
    if threshold is not None and not isinstance(threshold, (float, int)):
        raise RegimePortfolioError("non-numeric condition threshold")
    if isinstance(threshold, (int, float)) and not isfinite(threshold):
        raise RegimePortfolioError("nonfinite condition threshold")


def simulate_regime_portfolio(
    *,
    market: MarketDataSet,
    program: RegimeRouterSpec,
    strategies: Mapping[str, StrategyIR],
    values: Mapping[str, Sequence[float | None]],
    cost_model: CostModel,
    initial_cash: float = 10_000.0,
) -> RegimePortfolioResult:
    """Long/cash QQQ research: close signals, next-open fills, shared NAV.

    Under a flat/switch regime 'flatten_on_switch' liquidates the old route at
    the next open. 'hold_previous_until_exit' preserves existing sleeves until
    their own exit signal. Other strategy sizes are not silently leveraged.
    """
    if market.zone != DataZone.DEVELOPMENT:
        raise RegimePortfolioError("only development data is accessible")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise RegimePortfolioError("positive finite initial cash required")
    if len(market.bars) < 2 or len({bar.symbol for bar in market.bars}) != 1:
        raise RegimePortfolioError("single-symbol, at least two bars required")
    timestamps = [bar.timestamp for bar in market.bars]
    if timestamps != sorted(set(timestamps)):
        raise RegimePortfolioError("market bars require strictly increasing timestamps")
    if len({route.strategy_id for route in program.routes}) != len(program.routes):
        raise RegimePortfolioError("duplicate strategy sleeves are not supported")
    route_ids = {route.strategy_id for route in program.routes}
    if set(strategies) != route_ids:
        raise RegimePortfolioError("strategy IDs must exactly match routed sleeves")

    frame: dict[str, list[float | None]] = {}
    for alias, seq in values.items():
        if len(seq) != len(market.bars) or any(
            v is not None and (type(v) not in (int, float) or not isfinite(v))
            for v in seq
        ):
            raise RegimePortfolioError(f"missing or invalid aligned signal: {alias}")
        frame[alias] = list(seq)
    for route in program.routes:
        for condition in route.when.conditions:
            _require_operand(condition, frame)
        if route.when.conditions == []:
            raise RegimePortfolioError("empty regime route")
    for sid, strategy in strategies.items():
        if strategy.strategy_id != sid:
            raise RegimePortfolioError("strategy ID mismatch")
        if (
            strategy.risk.daily_loss_action != "none"
            or strategy.risk.daily_loss_limit_pct is not None
            or strategy.risk.max_concurrent_positions is not None
            or strategy.risk.max_total_exposure_pct is not None
            or strategy.risk.risk_appetite is not None
            or strategy.risk.loss_tolerance_pct is not None
        ):
            raise RegimePortfolioError("unsupported advanced risk policy")
        if not strategy.entry.conditions or not strategy.exit.conditions:
            raise RegimePortfolioError("empty executable strategy rules")
        for condition in (
            *strategy.entry.conditions, *strategy.exit.conditions, *strategy.regime_filters
        ):
            _require_operand(condition, frame)
    policy_hash = content_hash({
        "router": program.model_dump(mode="json"),
        "strategies": {
            sid: strategy.model_dump(mode="json", by_alias=True)
            for sid, strategy in sorted(strategies.items())
        },
        "dataset_hash": market.dataset_hash,
        "aligned_signal_hash": content_hash(frame),
        "cost_model": asdict(cost_model),
    })
    cash = initial_cash
    sleeves = {sid: _Sleeve() for sid in strategies}
    filled: list[SleeveFill] = []
    external: list[ExternalNetTrade] = []
    equities: list[float] = []
    cash_values: list[float] = []
    total_costs = 0.0

    for index, bar in enumerate(market.bars):
        sell_orders: dict[str, tuple[int, float]] = {}
        buy_orders: dict[str, tuple[int, float]] = {}
        for sid, sleeve in sleeves.items():
            if sleeve.pending_exit is not None:
                if sleeve.units > 0:
                    sell_orders[sid] = (sleeve.pending_exit, sleeve.units * bar.open)
                sleeve.pending_exit = None
            if sleeve.pending_entry is not None:
                if sleeve.units > 0:
                    raise RegimePortfolioError("duplicate entry into held strategy")
                buy_orders[sid] = sleeve.pending_entry
                sleeve.pending_entry = None

        sell_gross = sum(n for _, n in sell_orders.values())
        equity_open = cash + sum(s.units * bar.open for s in sleeves.values())
        buy_targets: dict[str, tuple[int, float]] = {
            sid: (signal_index, equity_open * allocation_pct / 100)
            for sid, (signal_index, allocation_pct) in buy_orders.items()
        }
        requested = sum(amount for _, amount in buy_targets.values())
        # Conservatively reduce requested buys rather than borrow money or
        # double-spend committed cash, even with old sleeves still held.
        available = cash + sell_gross
        scale = min(1.0, available / requested) if requested > 0 else 1.0
        buys = {
            sid: (signal_index, amount * scale)
            for sid, (signal_index, amount) in buy_targets.items()
        }
        buy_gross = sum(amount for _, amount in buys.values())
        net = buy_gross - sell_gross
        charge = (
            cost_model.calculate(
                abs(net), side="buy" if net > 0 else "sell", stress_multiplier=1.0
            ).total
            if abs(net) > 1e-9
            else 0.0
        )
        if charge < 0 or (net > 0 and charge >= net):
            raise RegimePortfolioError("net external trade costs exceed available notional")
        for sid, (signal_index, gross) in sell_orders.items():
            sleeve = sleeves[sid]
            allocated = charge * gross / sell_gross if net < 0 and sell_gross else 0.0
            filled.append(SleeveFill(
                sid, "sell", index, signal_index, bar.timestamp.isoformat(),
                sleeve.units, gross, allocated,
            ))
            sleeve.units = 0.0
            sleeve.entry_price = 0.0
            sleeve.peak_close = 0.0
        for sid, (signal_index, gross) in buys.items():
            if gross <= 0:
                continue
            sleeve = sleeves[sid]
            allocated = charge * gross / buy_gross if net > 0 and buy_gross else 0.0
            if allocated >= gross:
                raise RegimePortfolioError("allocated buy fee consumes budget")
            qty = (gross - allocated) / bar.open
            filled.append(SleeveFill(
                sid, "buy", index, signal_index, bar.timestamp.isoformat(),
                qty, gross, allocated,
            ))
            sleeve.units = qty
            sleeve.entry_price = bar.open
            sleeve.peak_close = bar.open

        # For buys, the commission reduces acquired units within budget; for
        # sells, the commission reduces proceeds. Internal sleeve transfers
        # are virtual and are not charged as duplicated exchange transactions.
        cash += sell_gross - buy_gross - (charge if net < 0 else 0.0)
        if cash < -1e-7:
            raise RegimePortfolioError("shared portfolio overdraft")
        cash = max(0.0, cash)
        total_costs += charge
        if abs(net) > 1e-9:
            external.append(ExternalNetTrade(
                "buy" if net > 0 else "sell",
                index,
                bar.timestamp.isoformat(),
                abs(net),
                (abs(net) - charge) / bar.open if net > 0 else abs(net) / bar.open,
                charge,
            ))
        chosen = resolve_regime_routes(program, frame, index)
        active = {route.strategy_id: route.allocation_pct for route in chosen}
        for sid, sleeve in sleeves.items():
            strategy = strategies[sid]
            if sleeve.units > 0:
                sleeve.peak_close = max(bar.close, sleeve.peak_close)
                wants_exit = (
                    _rules_match(
                        strategy.exit.conditions, strategy.exit.logic, frame, index
                    )
                    or _risk_exit(
                        strategy, sleeve.entry_price, bar.close, peak_close=sleeve.peak_close
                    )
                    or (
                        program.transition_policy == "flatten_on_switch"
                        and sid not in active
                    )
                )
                if wants_exit and index + 1 < len(market.bars):
                    sleeve.pending_exit = index
            elif sid in active and index + 1 < len(market.bars):
                if _regime_allows(strategy, frame, index) and _rules_match(
                    strategy.entry.conditions, strategy.entry.logic, frame, index
                ):
                    sleeve.pending_entry = (
                        index,
                        active[sid] * strategy.risk.position_size_pct / 100,
                    )
        marked = cash + sum(s.units * bar.close for s in sleeves.values())
        if marked <= 0 or not isfinite(marked):
            raise RegimePortfolioError("invalid shared equity")
        equities.append(marked)
        cash_values.append(cash)

    curve = tuple(equities)
    cash_curve = tuple(cash_values)
    digest = content_hash({
        "policy_hash": policy_hash,
        "market_hash": market.dataset_hash,
        "equity": curve,
        "cash": cash_curve,
        "sleeve_fills": [asdict(x) for x in filled],
        "external_net_trades": [asdict(x) for x in external],
        "research_only": True,
    })
    return RegimePortfolioResult(
        data_hash=market.dataset_hash,
        policy_hash=policy_hash,
        equity_curve=curve,
        cash_curve=cash_curve,
        sleeve_fills=tuple(filled),
        external_trades=tuple(external),
        total_costs=total_costs,
        trace_hash=digest,
    )
