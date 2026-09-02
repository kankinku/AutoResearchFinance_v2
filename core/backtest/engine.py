from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from math import isfinite

from core.costs.model import CostModel
from core.data.contracts import Bar, MarketDataSet, SeriesDataSet
from core.features.alignment import align_as_of
from core.features.calculators import FeatureCalculationError, calculate_feature
from core.features.contracts import FeatureSpec
from core.features.series import TimeFrame, resample_completed
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
    feature_values: Mapping[str, Sequence[float | None]] | None = None
    feature_specs: Mapping[str, FeatureSpec] | None = None
    feature_inputs: Mapping[str, Sequence[float | None]] | None = None
    external_series: SeriesDataSet | None = None


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
        values.update(
            _feature_values(
                request.dataset,
                strategy,
                request.feature_values,
                request.feature_specs,
                request.feature_inputs,
                request.external_series,
            )
        )
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
    inputs: dict[str, list[float | None]] = {
        field: [float(getattr(bar, field)) for bar in dataset.bars]
        for field in {"open", "high", "low", "close", "volume"}
    }
    result: dict[str, list[float | None]] = {}
    for name, spec in strategy.indicators.items():
        result[name] = _indicator(spec, inputs)
    result.update(inputs)
    return result


def _feature_values(
    dataset: MarketDataSet,
    strategy: StrategyIR,
    supplied: Mapping[str, Sequence[float | None]] | None,
    specs: Mapping[str, FeatureSpec] | None,
    inputs: Mapping[str, Sequence[float | None]] | None,
    external_series: SeriesDataSet | None = None,
) -> dict[str, list[float | None]]:
    if not strategy.features:
        return {}
    result: dict[str, list[float | None]] = {}
    for alias, reference in strategy.features.items():
        values: list[float | None]
        if supplied is not None and alias in supplied:
            values = list(supplied[alias])
        else:
            if specs is None or reference.feature_id not in specs or inputs is None:
                if specs is None or reference.feature_id not in specs:
                    raise ValueError(f"missing feature values for {alias!r}")
            spec = specs[reference.feature_id]
            if spec.status != "REGISTERED":
                raise ValueError(f"feature is not registered: {reference.feature_id!r}")
            resolved_inputs = dict(inputs or {})
            timeframe = spec.timeframe if reference.timeframe == "1d" else reference.timeframe
            if external_series is not None:
                target_timestamps = tuple(bar.timestamp for bar in dataset.bars)
                for input_name in spec.inputs:
                    if input_name in resolved_inputs:
                        continue
                    series_id = input_name.rsplit(".", maxsplit=1)[0]
                    observations = tuple(
                        observation
                        for observation in external_series.observations
                        if observation.series_id == series_id
                    )
                    if not observations:
                        continue
                    resampled = resample_completed(observations, TimeFrame(timeframe))
                    resolved_inputs[input_name] = align_as_of(target_timestamps, resampled)
            try:
                values = list(
                    calculate_feature(
                        spec.model_copy(update={"timeframe": timeframe}), resolved_inputs
                    )
                )
            except FeatureCalculationError as exc:
                raise ValueError(str(exc)) from exc
        if len(values) != len(dataset.bars):
            raise ValueError(f"feature values length mismatch for {alias!r}")
        lag = reference.lag_bars
        if specs is not None and reference.feature_id in specs:
            lag += specs[reference.feature_id].lag_bars
        result[alias] = _lag(values, lag)
    return result


def _lag(values: list[float | None], bars: int) -> list[float | None]:
    if bars <= 0:
        return values
    if bars >= len(values):
        return [None] * len(values)
    return [None] * bars + values[:-bars]


def _indicator(
    spec: IndicatorSpec, inputs: Mapping[str, Sequence[float | None]]
) -> list[float | None]:
    if not isinstance(spec, IndicatorSpec):
        try:
            spec = IndicatorSpec.model_validate(spec)
        except Exception as exc:
            raise ValueError("unsupported indicator specification") from exc
    kind = spec.type.upper()
    period = spec.period
    if period is None:
        raise ValueError(f"unsupported indicator {spec.type!r}")
    calculator = kind.lower()
    feature_inputs = {"close": inputs["close"]}
    if calculator in {"atr", "adx"}:
        feature_inputs = {field: inputs[field] for field in ("high", "low", "close")}
    elif calculator == "volume_breakout":
        feature_inputs = {"volume": inputs["volume"]}
    feature_spec = FeatureSpec(
        name=f"indicator_{calculator}",
        family="price",
        inputs=tuple(feature_inputs),
        calculator=calculator,
        lookback=period,
        parameters=spec.parameters,
        formula=f"{calculator}({', '.join(feature_inputs)})",
    )
    try:
        return list(calculate_feature(feature_spec, feature_inputs))
    except FeatureCalculationError as exc:
        raise ValueError(f"unsupported indicator {spec.type!r}: {exc}") from exc


def _rules_match(
    conditions: list[Condition], logic: str, values: dict[str, list[float | None]], index: int
) -> bool:
    outcomes = [
        _condition_match(condition, values, index) for condition in conditions if condition.enabled
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
    return (strategy.risk.stop_loss_pct > 0 and move_pct <= -strategy.risk.stop_loss_pct) or (
        strategy.risk.take_profit_pct > 0 and move_pct >= strategy.risk.take_profit_pct
    )


def _cost(cost_model: CostModel | None, notional: float, side: str) -> float:
    if cost_model is None:
        return 0.0
    return cost_model.calculate(notional, side=side, stress_multiplier=1.0).total


def _trade(bar: Bar, side: str, quantity: float, cost: float) -> Trade:
    timestamp = bar.timestamp.isoformat()
    price = bar.close
    return Trade(timestamp, side, price, quantity, quantity * price, cost)
