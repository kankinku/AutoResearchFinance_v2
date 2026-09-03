from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
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
    cost_stress_multiplier: float = 1.0


@dataclass(frozen=True)
class Trade:
    timestamp: str
    side: str
    price: float
    quantity: float
    notional: float
    cost: float
    symbol: str = ""


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    strategy_hash: str
    data_hash: str
    equity_curve: tuple[float, ...]
    equity_curve_hash: str
    exit_status: str
    trades: tuple[Trade, ...] = ()


@dataclass
class _SymbolState:
    bars: tuple[Bar, ...]
    values: dict[str, list[float | None]]
    index_by_timestamp: dict[datetime, int]
    units: float = 0.0
    entry_price: float = 0.0
    pending: str | None = None
    last_close: float = 0.0


class BacktestEngine:
    def run(self, request: BacktestRequest) -> BacktestResult:
        if not request.run_id or request.initial_cash <= 0:
            raise ValueError("run_id and positive initial cash are required")
        if request.cost_stress_multiplier < 0:
            raise ValueError("cost stress multiplier cannot be negative")
        if request.strategy is not None:
            return self._run_strategy(request)
        symbols = tuple(sorted({bar.symbol for bar in request.dataset.bars}))
        if len(symbols) > 1:
            return self._run_multi_symbol_passthrough(request, symbols)
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

    def _run_multi_symbol_passthrough(
        self, request: BacktestRequest, symbols: tuple[str, ...]
    ) -> BacktestResult:
        allocation = request.initial_cash / len(symbols)
        timelines: dict[str, dict[datetime, float]] = {}
        for symbol in symbols:
            bars = tuple(bar for bar in request.dataset.bars if bar.symbol == symbol)
            symbol_curve = [allocation]
            for previous, current in pairwise(bars):
                symbol_curve.append(symbol_curve[-1] * (current.close / previous.close))
            timelines[symbol] = {
                bar.timestamp: value for bar, value in zip(bars, symbol_curve, strict=True)
            }
        timestamps = sorted(
            {timestamp for timeline in timelines.values() for timestamp in timeline}
        )
        latest = {symbol: allocation for symbol in symbols}
        equity_curve: list[float] = []
        for timestamp in timestamps:
            for symbol in symbols:
                if timestamp in timelines[symbol]:
                    latest[symbol] = timelines[symbol][timestamp]
            equity_curve.append(sum(latest.values()))
        total_curve = tuple(equity_curve)
        return BacktestResult(
            request.run_id,
            request.strategy_hash,
            request.dataset.dataset_hash,
            total_curve,
            content_hash(total_curve),
            "SUCCEEDED",
        )

    def _run_strategy(self, request: BacktestRequest) -> BacktestResult:
        symbols = tuple(sorted({bar.symbol for bar in request.dataset.bars}))
        if len(symbols) > 1:
            return self._run_multi_symbol_strategy(request, symbols)
        return self._run_single_symbol_strategy(request)

    def _run_multi_symbol_strategy(
        self, request: BacktestRequest, symbols: tuple[str, ...]
    ) -> BacktestResult:
        strategy = request.strategy
        assert strategy is not None
        allocation = request.initial_cash / len(symbols)
        full_width = len(request.dataset.bars)
        states: dict[str, _SymbolState] = {}
        for symbol in symbols:
            indices = tuple(
                index for index, bar in enumerate(request.dataset.bars) if bar.symbol == symbol
            )
            bars = tuple(request.dataset.bars[index] for index in indices)
            dataset = MarketDataSet(request.dataset.version, request.dataset.zone, bars)
            values = _indicator_values(dataset, strategy)
            values.update(
                _feature_values(
                    dataset,
                    strategy,
                    _slice_mapping(request.feature_values, indices, full_width),
                    request.feature_specs,
                    _slice_mapping(request.feature_inputs, indices, full_width),
                    request.external_series,
                )
            )
            states[symbol] = _SymbolState(
                bars,
                values,
                {bar.timestamp: index for index, bar in enumerate(bars)},
                last_close=bars[0].close,
            )

        timestamps = sorted({bar.timestamp for state in states.values() for bar in state.bars})
        cash = request.initial_cash
        current_day: date | None = None
        day_start_equity = cash
        daily_loss_blocked = False
        stopped = False
        equity_curve: list[float] = []
        trades: list[Trade] = []
        for timestamp in timestamps:
            current_bars = {
                symbol: state.bars[state.index_by_timestamp[timestamp]]
                for symbol, state in states.items()
                if timestamp in state.index_by_timestamp
            }
            first_bar = current_bars[next(iter(current_bars))]
            bar_day = first_bar.timestamp.date()
            exposure_at_open = sum(
                state.units
                * current_bars.get(symbol, first_bar).open
                if symbol in current_bars
                else state.units * state.last_close
                for symbol, state in states.items()
            )
            if bar_day != current_day:
                current_day = bar_day
                day_start_equity = cash + exposure_at_open
                daily_loss_blocked = False
            if _daily_loss_breached(strategy, day_start_equity, cash + exposure_at_open):
                daily_loss_blocked = True

            for symbol in symbols:
                state = states[symbol]
                bar = current_bars.get(symbol)
                if bar is None or state.pending != "exit" or state.units <= 0:
                    continue
                notional = state.units * bar.open
                cost = _cost(
                    request.cost_model,
                    notional,
                    "sell",
                    request.cost_stress_multiplier,
                )
                cash += notional - cost
                trades.append(_trade(bar, "sell", state.units, cost, price=bar.open))
                state.units = 0.0
                state.entry_price = 0.0
                state.pending = None

            for symbol in symbols:
                state = states[symbol]
                bar = current_bars.get(symbol)
                if bar is None or state.pending != "entry" or state.units > 0:
                    continue
                notional = allocation * strategy.risk.position_size_pct / 100
                current_exposure = sum(
                    candidate.units
                    * current_bars.get(candidate_symbol, bar).open
                    if candidate_symbol in current_bars
                    else candidate.units * candidate.last_close
                    for candidate_symbol, candidate in states.items()
                )
                equity_at_open = cash + current_exposure
                concurrent = sum(candidate.units > 0 for candidate in states.values())
                max_concurrent = strategy.risk.max_concurrent_positions
                allowed_concurrent = (
                    max_concurrent is None or concurrent < max_concurrent
                )
                if (
                    not daily_loss_blocked
                    and not stopped
                    and allowed_concurrent
                    and cash + 1e-9 >= notional
                    and _exposure_allows(
                        strategy, notional, equity_at_open, current_exposure
                    )
                ):
                    cost = _cost(
                        request.cost_model,
                        notional,
                        "buy",
                        request.cost_stress_multiplier,
                    )
                    state.units = max(0.0, (notional - cost) / bar.open)
                    cash -= notional
                    state.entry_price = bar.open
                    trades.append(_trade(bar, "buy", state.units, cost, price=bar.open))
                state.pending = None

            for symbol in symbols:
                state = states[symbol]
                bar = current_bars.get(symbol)
                if bar is None:
                    continue
                index = state.index_by_timestamp[timestamp]
                state.last_close = bar.close
                if state.units > 0:
                    if _rules_match(
                        strategy.exit.conditions, strategy.exit.logic, state.values, index
                    ) or _risk_exit(strategy, state.entry_price, bar.close):
                        state.pending = "exit"
                elif (
                    not daily_loss_blocked
                    and not stopped
                    and _rules_match(
                        strategy.entry.conditions, strategy.entry.logic, state.values, index
                    )
                ):
                    state.pending = "entry"

            marked_equity = cash + sum(
                state.units * current_bars[symbol].close
                if symbol in current_bars
                else state.units * state.last_close
                for symbol, state in states.items()
            )
            if _daily_loss_breached(strategy, day_start_equity, marked_equity):
                daily_loss_blocked = True
                if strategy.risk.daily_loss_action in {"reduce", "stop"}:
                    for state in states.values():
                        if state.units > 0:
                            state.pending = "exit"
                if strategy.risk.daily_loss_action == "stop":
                    stopped = True
            equity_curve.append(marked_equity)

        trades_tuple = tuple(
            sorted(trades, key=lambda trade: (trade.timestamp, trade.symbol, trade.side))
        )
        return BacktestResult(
            request.run_id,
            content_hash(strategy.model_dump(mode="json", by_alias=True)),
            request.dataset.dataset_hash,
            tuple(equity_curve),
            content_hash(tuple(equity_curve)),
            "SUCCEEDED",
            trades_tuple,
        )

    def _run_single_symbol_strategy(self, request: BacktestRequest) -> BacktestResult:
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
        pending: str | None = None
        current_day: date | None = None
        day_start_equity = cash
        daily_loss_blocked = False
        stopped = False
        for index, bar in enumerate(request.dataset.bars):
            bar_day = bar.timestamp.date()
            if bar_day != current_day:
                current_day = bar_day
                day_start_equity = cash + units * bar.open
                daily_loss_blocked = False
            if _daily_loss_breached(
                strategy, day_start_equity, cash + units * bar.open
            ):
                daily_loss_blocked = True

            if pending == "exit" and units > 0:
                notional = units * bar.open
                cost = _cost(
                    request.cost_model,
                    notional,
                    "sell",
                    request.cost_stress_multiplier,
                )
                cash += notional - cost
                trades.append(_trade(bar, "sell", units, cost, price=bar.open))
                units = 0.0
                entry_price = 0.0
            elif pending == "entry" and units == 0:
                notional = cash * strategy.risk.position_size_pct / 100
                if (
                    not daily_loss_blocked
                    and not stopped
                    and _entry_within_exposure_limit(strategy, notional, cash, units, bar.open)
                ):
                    cost = _cost(
                        request.cost_model,
                        notional,
                        "buy",
                        request.cost_stress_multiplier,
                    )
                    units = max(0.0, (notional - cost) / bar.open)
                    cash -= notional
                    entry_price = bar.open
                    trades.append(_trade(bar, "buy", units, cost, price=bar.open))
            pending = None

            if units > 0:
                exit_signal = _rules_match(
                    strategy.exit.conditions, strategy.exit.logic, values, index
                )
                if exit_signal or _risk_exit(strategy, entry_price, bar.close):
                    pending = "exit"
            elif (
                not daily_loss_blocked
                and not stopped
                and _rules_match(strategy.entry.conditions, strategy.entry.logic, values, index)
            ):
                pending = "entry"
            marked_equity = cash + units * bar.close
            if _daily_loss_breached(strategy, day_start_equity, marked_equity):
                daily_loss_blocked = True
                if strategy.risk.daily_loss_action in {"reduce", "stop"} and units > 0:
                    pending = "exit"
                if strategy.risk.daily_loss_action == "stop":
                    stopped = True
            equity.append(marked_equity)
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
            selected_inputs = reference.inputs or spec.inputs
            selected_parameters = dict(spec.parameters)
            selected_parameters.update(reference.parameters)
            timeframe = spec.timeframe if reference.timeframe == "1d" else reference.timeframe
            if external_series is not None:
                target_timestamps = tuple(bar.timestamp for bar in dataset.bars)
                for input_name in selected_inputs:
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
                        spec.model_copy(
                            update={
                                "inputs": tuple(selected_inputs),
                                "parameters": selected_parameters,
                                "lookback": reference.lookback or spec.lookback,
                                "timeframe": timeframe,
                            }
                        ),
                        resolved_inputs,
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
    period = spec.period or 1
    calculator = kind.lower()
    feature_inputs = {"close": inputs["close"]}
    if calculator in {"atr", "adx"}:
        feature_inputs = {field: inputs[field] for field in ("high", "low", "close")}
    elif calculator == "ibs":
        feature_inputs = {
            "close": inputs["close"],
            "high": inputs["high"],
            "low": inputs["low"],
        }
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
    if condition.right is not None:
        target_value = values[condition.right][index]
        if target_value is None:
            return False
        target = float(target_value)
    else:
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


def _cost(
    cost_model: CostModel | None,
    notional: float,
    side: str,
    stress_multiplier: float,
) -> float:
    if cost_model is None:
        return 0.0
    return cost_model.calculate(
        notional, side=side, stress_multiplier=stress_multiplier
    ).total


def _trade(
    bar: Bar, side: str, quantity: float, cost: float, *, price: float | None = None
) -> Trade:
    timestamp = bar.timestamp.isoformat()
    execution_price = bar.close if price is None else price
    return Trade(
        timestamp,
        side,
        execution_price,
        quantity,
        quantity * execution_price,
        cost,
        bar.symbol,
    )


def _entry_within_exposure_limit(
    strategy: StrategyIR, planned_notional: float, cash: float, units: float, price: float
) -> bool:
    equity = cash + units * price
    current_exposure = units * price
    return _exposure_allows(strategy, planned_notional, equity, current_exposure)


def _exposure_allows(
    strategy: StrategyIR, planned_notional: float, equity: float, current_exposure: float
) -> bool:
    limit = strategy.risk.max_total_exposure_pct
    if limit is None:
        return True
    allowed_exposure = equity * limit / 100
    return current_exposure + planned_notional <= allowed_exposure + 1e-9


def _daily_loss_breached(
    strategy: StrategyIR, day_start_equity: float, current_equity: float
) -> bool:
    limit = strategy.risk.daily_loss_limit_pct
    if limit is None or strategy.risk.daily_loss_action == "none" or day_start_equity <= 0:
        return False
    loss_pct = (day_start_equity - current_equity) / day_start_equity * 100
    return loss_pct >= limit - 1e-9


def _slice_mapping(
    values: Mapping[str, Sequence[float | None]] | None,
    indices: Sequence[int],
    full_width: int,
) -> Mapping[str, Sequence[float | None]] | None:
    if values is None:
        return None
    return {
        name: tuple(series[index] for index in indices)
        if len(series) == full_width
        else tuple(series)
        for name, series in values.items()
    }
