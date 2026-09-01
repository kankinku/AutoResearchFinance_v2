from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import isfinite

from core.costs.model import CostModel
from core.data.contracts import Bar, MarketDataSet
from core.integrity.hashes import content_hash
from strategy_ir.schema import Condition, IndicatorSpec, StrategyIR


@dataclass(frozen=True)
class BacktestRequest:
    run_id: str
    strategy_hash: str
    dataset: MarketDataSet
    initial_cash: float
    strategy: StrategyIR | None = None
    cost_model: CostModel | None = None


@dataclass(frozen=True)
class Trade:
    timestamp: str
    side: str
    price: float
    quantity: float
    notional: float
    cost: float


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    strategy_hash: str
    data_hash: str
    equity_curve: tuple[float, ...]
    equity_curve_hash: str
    exit_status: str
    trades: tuple[Trade, ...] = ()


class BacktestEngine:
    def run(self, request: BacktestRequest) -> BacktestResult:
        if not request.run_id or request.initial_cash <= 0:
            raise ValueError("run_id and positive initial cash are required")
        if request.strategy is not None:
            return self._run_strategy(request)
        equity = [request.initial_cash]
        for previous, current in pairwise(request.dataset.bars):
            equity.append(equity[-1] * (current.close / previous.close))
        curve = tuple(equity)
        return BacktestResult(
            request.run_id,
            request.strategy_hash,
            request.dataset.dataset_hash,
            curve,
            content_hash(curve),
            "SUCCEEDED",
        )

    def _run_strategy(self, request: BacktestRequest) -> BacktestResult:
        strategy = request.strategy
        assert strategy is not None
        values = _indicator_values(request.dataset, strategy)
        strategy_hash = content_hash(strategy.model_dump(mode="json", by_alias=True))
        cash = request.initial_cash
        units = 0.0
        entry_price = 0.0
        equity: list[float] = []
        trades: list[Trade] = []
        for index, bar in enumerate(request.dataset.bars):
            should_exit = units > 0 and (
                _rules_match(strategy.exit.conditions, strategy.exit.logic, values, index)
                or _risk_exit(strategy, entry_price, bar.close)
            )
            if should_exit:
                notional = units * bar.close
                cost = _cost(request.cost_model, notional, "sell")
                cash += notional - cost
                trades.append(_trade(bar, "sell", units, cost))
                units = 0.0
                entry_price = 0.0
            should_enter = units == 0 and _rules_match(
                strategy.entry.conditions, strategy.entry.logic, values, index
            )
            if should_enter:
                notional = cash * strategy.risk.position_size_pct / 100
                cost = _cost(request.cost_model, notional, "buy")
                units = max(0.0, (notional - cost) / bar.close)
                cash -= notional
                entry_price = bar.close
                trades.append(_trade(bar, "buy", units, cost))
            equity.append(cash + units * bar.close)
        return BacktestResult(
            request.run_id,
            strategy_hash,
            request.dataset.dataset_hash,
            tuple(equity),
            content_hash(tuple(equity)),
            "SUCCEEDED",
            tuple(trades),
        )


def _indicator_values(
    dataset: MarketDataSet, strategy: StrategyIR
) -> dict[str, list[float | None]]:
    closes = [bar.close for bar in dataset.bars]
    result: dict[str, list[float | None]] = {}
    for name, spec in strategy.indicators.items():
        result[name] = _indicator(spec, closes)
    for field in {"open", "high", "low", "close", "volume"}:
        result[field] = [float(getattr(bar, field)) for bar in dataset.bars]
    return result


def _indicator(spec: IndicatorSpec, closes: list[float]) -> list[float | None]:
    if not isinstance(spec, IndicatorSpec):
        raise ValueError("unsupported indicator specification")
    kind = spec.type.upper()
    period = spec.period
    if period is None or kind not in {"SMA", "EMA", "RSI"}:
        raise ValueError(f"unsupported indicator {spec.type!r}")
    if kind == "SMA":
        return [None if index + 1 < period else sum(closes[index + 1 - period : index + 1]) / period
                for index in range(len(closes))]
    if kind == "EMA":
        values: list[float | None] = [None] * len(closes)
        if len(closes) < period:
            return values
        current = sum(closes[:period]) / period
        values[period - 1] = current
        alpha = 2 / (period + 1)
        for index in range(period, len(closes)):
            current = (closes[index] - current) * alpha + current
            values[index] = current
        return values
    values = [None] * len(closes)
    for index in range(period, len(closes)):
        window = range(index - period + 1, index + 1)
        gains = [max(0.0, closes[pos] - closes[pos - 1]) for pos in window]
        losses = [max(0.0, closes[pos - 1] - closes[pos]) for pos in window]
        average_loss = sum(losses) / period
        values[index] = (
            100.0
            if average_loss == 0
            else 100 - 100 / (1 + (sum(gains) / period) / average_loss)
        )
    return values


def _rules_match(
    conditions: list[Condition], logic: str, values: dict[str, list[float | None]], index: int
) -> bool:
    outcomes = [
        _condition_match(condition, values, index)
        for condition in conditions
        if condition.enabled
    ]
    return bool(outcomes) and (all(outcomes) if logic == "AND" else any(outcomes))


def _condition_match(
    condition: Condition, values: dict[str, list[float | None]], index: int
) -> bool:
    current = values[condition.left][index]
    if current is None:
        return False
    if condition.op in {"cross_above", "cross_below"}:
        if index == 0 or condition.right is None:
            return False
        right = values[condition.right][index]
        previous_left = values[condition.left][index - 1]
        previous_right = values[condition.right][index - 1]
        if right is None or previous_left is None or previous_right is None:
            return False
        return (
            previous_left <= previous_right and current > right
            if condition.op == "cross_above"
            else previous_left >= previous_right and current < right
        )
    assert condition.value is not None
    target = float(condition.value)
    if not isfinite(target):
        return False
    return {
        "less_than": current < target,
        "less_equal": current <= target,
        "greater_than": current > target,
        "greater_equal": current >= target,
        "equal": current == target,
    }[condition.op]


def _risk_exit(strategy: StrategyIR, entry_price: float, price: float) -> bool:
    if entry_price <= 0:
        return False
    move_pct = (price / entry_price - 1) * 100
    return (
        strategy.risk.stop_loss_pct > 0 and move_pct <= -strategy.risk.stop_loss_pct
    ) or (strategy.risk.take_profit_pct > 0 and move_pct >= strategy.risk.take_profit_pct)


def _cost(cost_model: CostModel | None, notional: float, side: str) -> float:
    if cost_model is None:
        return 0.0
    return cost_model.calculate(notional, side=side, stress_multiplier=1.0).total


def _trade(bar: Bar, side: str, quantity: float, cost: float) -> Trade:
    timestamp = bar.timestamp.isoformat()
    price = bar.close
    return Trade(timestamp, side, price, quantity, quantity * price, cost)
