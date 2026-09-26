from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.backtest.engine import BacktestEngine, BacktestRequest, Trade
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import Bar, DataZone, MarketDataSet, SeriesDataSet
from core.data.timebase import equity_returns, equity_timestamps, periods_per_year
from core.features.contracts import FeatureSpec
from core.validation.walk_forward import walk_forward_splits
from evaluation.benchmark import BenchmarkComparison, BenchmarkData, compare_benchmarks
from evaluation.metrics import Metrics, calculate_metrics
from evaluation.risk import RiskEvaluation, evaluate_risk_policy
from evaluation.robustness import (
    cpcv_return_scores,
    probability_backtest_overfitting,
    robust_statistics,
)
from evaluation.selector import FunnelConfig, FunnelInput, FunnelResult, select_candidate
from evaluation.yearly import summarize_yearly_performance
from experiments.candidate_generator import Candidate, generate_candidates
from memory.knowledge import extract_knowledge
from mutation.engine import MutationOperation
from mutation.parameter import BayesianObservation, ParameterDomain
from orchestration.generation import CANONICAL_STAGES
from strategy_ir.schema import StrategyIR


@dataclass(frozen=True)
class GenerationPipelineResult:
    stages: tuple[str, ...]
    candidates: tuple[Candidate, ...]
    funnel: tuple[FunnelResult, ...]
    knowledge: dict[str, object]


@dataclass(frozen=True)
class _CandidateEvaluation:
    candidate: Candidate
    fast_metrics: Metrics
    full_metrics: Metrics
    stressed_metrics: Metrics
    trades: tuple[Trade, ...]
    full_equity: tuple[float, ...]
    fast_benchmark: BenchmarkComparison | None
    full_benchmark: BenchmarkComparison | None
    risk_evaluation: RiskEvaluation
    validation_folds: tuple[dict[str, object], ...]
    yearly_metrics: tuple[dict[str, object], ...]
    returns: tuple[float, ...]


class GenerationPipeline:
    """Local end-to-end generation loop over immutable data and deterministic workers."""

    def __init__(self, *, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()
        self.cost_model = CostModel(
            "cost-v1", commission_bps=1.0, spread_bps=2.0, slippage=SlippageModel(5.0)
        )

    def run(
        self,
        *,
        parent: StrategyIR,
        dataset: MarketDataSet,
        operations: tuple[MutationOperation, ...],
        domains: tuple[ParameterDomain, ...],
        method: str,
        count: int,
        seed: int,
        funnel: FunnelConfig,
        observations: list[BayesianObservation] | None = None,
        benchmark_data: BenchmarkData | None = None,
        feature_values: Mapping[str, Sequence[float | None]] | None = None,
        feature_specs: Mapping[str, FeatureSpec] | None = None,
        feature_inputs: Mapping[str, Sequence[float | None]] | None = None,
        external_series: SeriesDataSet | None = None,
    ) -> GenerationPipelineResult:
        if DataZone(dataset.zone) is not DataZone.DEVELOPMENT:
            raise PermissionError("generation research requires development market data")
        if (
            external_series is not None
            and DataZone(external_series.zone) is not DataZone.DEVELOPMENT
        ):
            raise PermissionError("generation research requires development series data")

        candidates = generate_candidates(
            parent,
            operations,
            domains,
            method=method,
            count=count,
            seed=seed,
            observations=observations,
        )
        fast_dataset = _fast_slice(dataset)
        fast_width = len(fast_dataset.bars)
        fast_features = _slice_feature_values(feature_values, fast_width)
        fast_inputs = _slice_feature_values(feature_inputs, fast_width)
        fast_benchmark_data = (
            benchmark_data.slice(_timestamp_count(fast_dataset)) if benchmark_data else None
        )

        evaluated: list[_CandidateEvaluation] = []
        for candidate in candidates:
            fast_metrics, _, fast_equity = self._evaluate(
                candidate,
                fast_dataset,
                "fast",
                fast_features,
                feature_specs,
                fast_inputs,
                external_series,
            )
            full_metrics, trades, full_equity = self._evaluate(
                candidate,
                dataset,
                "full",
                feature_values,
                feature_specs,
                feature_inputs,
                external_series,
            )
            stressed_metrics, _, _ = self._evaluate(
                candidate,
                dataset,
                "stress",
                feature_values,
                feature_specs,
                feature_inputs,
                external_series,
                cost_stress_multiplier=2.0,
            )
            risk_evaluation = evaluate_risk_policy(
                full_equity,
                candidate.strategy.risk,
                timestamps=equity_timestamps(dataset, len(full_equity)),
            )
            fast_benchmark = _compare(
                fast_equity,
                fast_benchmark_data,
                periods_per_year=periods_per_year(fast_dataset),
            )
            full_benchmark = _compare(
                full_equity,
                benchmark_data,
                periods_per_year=periods_per_year(dataset),
            )
            validation_folds = self._temporal_holdout_evidence(
                candidate,
                dataset,
                funnel,
                feature_values,
                feature_specs,
                feature_inputs,
                external_series,
                benchmark_data,
            )
            yearly_metrics = summarize_yearly_performance(dataset, full_equity, trades)
            evaluated.append(
                _CandidateEvaluation(
                    candidate=candidate,
                    fast_metrics=fast_metrics,
                    full_metrics=full_metrics,
                    stressed_metrics=stressed_metrics,
                    trades=trades,
                    full_equity=full_equity,
                    fast_benchmark=fast_benchmark,
                    full_benchmark=full_benchmark,
                    risk_evaluation=risk_evaluation,
                    validation_folds=validation_folds,
                    yearly_metrics=yearly_metrics,
                    returns=equity_returns(full_equity),
                )
            )

        pbo: float | None = None
        if len(evaluated) >= 2:
            try:
                pbo = probability_backtest_overfitting(
                    tuple(item.returns for item in evaluated)
                )
            except ValueError:
                pbo = None

        results: list[FunnelResult] = []
        for item in evaluated:
            candidate = item.candidate
            validation_scores = tuple(
                float(value)
                for fold in item.validation_folds
                if isinstance((value := fold.get("strategy_total_return")), (int, float))
            )
            try:
                resampling_scores = cpcv_return_scores(item.returns)
            except ValueError:
                resampling_scores = validation_scores
            complexity = (
                len(candidate.strategy.indicators)
                + len(candidate.strategy.entry.conditions)
                + len(candidate.strategy.exit.conditions)
            )
            robust = robust_statistics(
                base_return=item.full_metrics.total_return,
                stressed_return=item.stressed_metrics.total_return,
                parameter_scores=resampling_scores,
                sharpe=item.full_metrics.sharpe or 0.0,
                trials=max(1, len(candidates)),
                observations=len(item.returns),
                complexity=complexity,
                pbo=pbo,
            )
            validation_passed = bool(item.validation_folds) and all(
                bool(fold["passed"]) for fold in item.validation_folds
            )
            results.append(
                select_candidate(
                    FunnelInput(
                        candidate.candidate_hash,
                        candidate.strategy.family,
                        item.fast_metrics,
                        item.full_metrics,
                        robust,
                        validation_passed,
                        item.fast_benchmark,
                        item.full_benchmark,
                        item.risk_evaluation,
                        tuple(
                            sorted(ref.feature_id for ref in candidate.strategy.features.values())
                        ),
                        candidate.parameters,
                        dataset.dataset_hash,
                        external_series.dataset_hash if external_series is not None else None,
                        item.validation_folds,
                        item.yearly_metrics,
                        _feature_lineage(candidate.strategy, feature_specs),
                    ),
                    funnel,
                )
            )
        knowledge = extract_knowledge(generation=parent.generation + 1, results=tuple(results))
        return GenerationPipelineResult(CANONICAL_STAGES, candidates, tuple(results), knowledge)

    def _temporal_holdout_evidence(
        self,
        candidate: Candidate,
        dataset: MarketDataSet,
        funnel: FunnelConfig,
        feature_values: Mapping[str, Sequence[float | None]] | None,
        feature_specs: Mapping[str, FeatureSpec] | None,
        feature_inputs: Mapping[str, Sequence[float | None]] | None,
        external_series: SeriesDataSet | None,
        benchmark_data: BenchmarkData | None,
    ) -> tuple[dict[str, object], ...]:
        timestamps = tuple(sorted({bar.timestamp for bar in dataset.bars}))
        timestamp_indices = tuple(range(len(timestamps)))
        splits = walk_forward_splits(
            timestamp_indices,
            train_size=max(1, len(timestamp_indices) // 2),
            test_size=max(1, len(timestamp_indices) // 4),
            step=max(1, len(timestamp_indices) // 4),
        )
        evidence: list[dict[str, object]] = []
        for fold_index, (train_indices, test_indices) in enumerate(splits):
            test_timestamps = {timestamps[index] for index in test_indices}
            test_bar_indices = tuple(
                index
                for index, bar in enumerate(dataset.bars)
                if bar.timestamp in test_timestamps
            )
            test_dataset = _select_dataset(dataset, test_bar_indices)
            test_feature_values = _select_feature_values(feature_values, test_bar_indices)
            test_feature_inputs = _select_feature_values(feature_inputs, test_bar_indices)
            metrics, _, equity = self._evaluate(
                candidate,
                test_dataset,
                f"validation-{fold_index}",
                test_feature_values,
                feature_specs,
                test_feature_inputs,
                external_series,
            )
            comparison = (
                _compare(
                    equity,
                    benchmark_data.select(test_indices),
                    periods_per_year=periods_per_year(test_dataset),
                )
                if benchmark_data is not None
                else None
            )
            target_passed = (
                comparison is not None
                and (
                    funnel.min_qqq_cagr_delta is None
                    or comparison.qqq_cagr_delta >= funnel.min_qqq_cagr_delta
                )
            )
            return_passed = metrics.total_return >= funnel.min_full_return
            trade_passed = metrics.trade_count >= funnel.min_full_trades
            failure_checks = [
                ("trade_count", not trade_passed),
                ("total_return", not return_passed),
            ]
            if funnel.min_qqq_cagr_delta is not None:
                failure_checks.append(("qqq_cagr_delta", not target_passed))
            passed = trade_passed and return_passed and (
                target_passed if funnel.min_qqq_cagr_delta is not None else True
            )
            evidence.append(
                {
                    "fold": fold_index,
                    "method": "temporal_holdout",
                    "selection_applied": False,
                    "train_start": train_indices[0],
                    "train_end": train_indices[-1],
                    "test_start": test_indices[0],
                    "test_end": test_indices[-1],
                    "train_start_at": timestamps[train_indices[0]].isoformat(),
                    "train_end_at": timestamps[train_indices[-1]].isoformat(),
                    "test_start_at": timestamps[test_indices[0]].isoformat(),
                    "test_end_at": timestamps[test_indices[-1]].isoformat(),
                    "strategy_total_return": metrics.total_return,
                    "strategy_cagr": metrics.cagr,
                    "trade_count": metrics.trade_count,
                    "max_drawdown": metrics.max_drawdown,
                    "qqq_cagr": comparison.qqq_cagr if comparison is not None else None,
                    "qqq_cagr_delta": (
                        comparison.qqq_cagr_delta if comparison is not None else None
                    ),
                    "passed": passed,
                    "failure_reasons": [
                        reason
                        for reason, condition in failure_checks
                        if condition
                    ],
                }
            )
        return tuple(evidence)


    def _evaluate(
        self,
        candidate: Candidate,
        dataset: MarketDataSet,
        run_kind: str,
        feature_values: Mapping[str, Sequence[float | None]] | None = None,
        feature_specs: Mapping[str, FeatureSpec] | None = None,
        feature_inputs: Mapping[str, Sequence[float | None]] | None = None,
        external_series: SeriesDataSet | None = None,
        cost_stress_multiplier: float = 1.0,
    ) -> tuple[Metrics, tuple[Trade, ...], tuple[float, ...]]:
        backtest = self.engine.run(
            BacktestRequest(
                f"{candidate.candidate_hash}-{run_kind}",
                candidate.candidate_hash,
                dataset,
                100_000.0,
                strategy=candidate.strategy,
                feature_values=feature_values,
                feature_specs=feature_specs,
                feature_inputs=feature_inputs,
                external_series=external_series,
                cost_model=self.cost_model,
                cost_stress_multiplier=cost_stress_multiplier,
            )
        )
        pnls = _closed_trade_pnls(backtest.trades)
        metrics = calculate_metrics(
            backtest.equity_curve,
            pnls,
            periods_per_year=periods_per_year(dataset),
            turnover=sum(trade.notional for trade in backtest.trades),
            exposure=len(pnls) / max(len(backtest.equity_curve), 1),
        )
        return (
            metrics,
            backtest.trades,
            backtest.equity_curve,
        )


def _feature_lineage(
    strategy: StrategyIR, feature_specs: Mapping[str, FeatureSpec] | None
) -> tuple[Mapping[str, object], ...]:
    if not strategy.features:
        return ()
    lineage: list[Mapping[str, object]] = []
    for alias, reference in sorted(strategy.features.items()):
        spec = feature_specs.get(reference.feature_id) if feature_specs is not None else None
        if spec is None:
            lineage.append(
                {
                    "alias": alias,
                    "feature_id": reference.feature_id,
                    "status": "MISSING",
                }
            )
            continue
        parameters = dict(spec.parameters)
        parameters.update(reference.parameters)
        lineage.append(
            {
                "alias": alias,
                "feature_id": spec.name,
                "canonical_id": spec.canonical_id,
                "inputs": list(reference.inputs or spec.inputs),
                "timeframe": reference.timeframe if reference.timeframe != "1d" else spec.timeframe,
                "lag_bars": reference.lag_bars + spec.lag_bars,
                "lookback": reference.lookback or spec.lookback,
                "parameters": parameters,
                "implementation_hash": spec.implementation_hash,
                "source_repositories": list(spec.source_repositories),
                "source_licenses": list(spec.source_licenses),
                "status": spec.status,
            }
        )
    return tuple(lineage)


def _fast_slice(dataset: MarketDataSet) -> MarketDataSet:
    bars: list[Bar] = []
    for symbol in sorted({bar.symbol for bar in dataset.bars}):
        symbol_bars = tuple(bar for bar in dataset.bars if bar.symbol == symbol)
        width = min(len(symbol_bars), max(2, len(symbol_bars) // 2))
        bars.extend(symbol_bars[:width])
    return MarketDataSet(
        dataset.version, dataset.zone, tuple(bars), dataset.timeframe, dataset.calendar
    )


def _timestamp_count(dataset: MarketDataSet) -> int:
    return len({bar.timestamp for bar in dataset.bars})


def _closed_trade_pnls(trades: tuple[Trade, ...]) -> tuple[float, ...]:
    buys: dict[str, list[Trade]] = {}
    pnls: list[float] = []
    for trade in trades:
        symbol_buys = buys.setdefault(trade.symbol, [])
        if trade.side == "buy":
            symbol_buys.append(trade)
        elif symbol_buys:
            buy = symbol_buys.pop(0)
            pnls.append((trade.price - buy.price) * trade.quantity - trade.cost - buy.cost)
    return tuple(pnls)


def _slice_feature_values(
    feature_values: Mapping[str, Sequence[float | None]] | None, width: int
) -> Mapping[str, Sequence[float | None]] | None:
    if feature_values is None:
        return None
    return {name: tuple(values[:width]) for name, values in feature_values.items()}


def _select_dataset(dataset: MarketDataSet, indices: Sequence[int]) -> MarketDataSet:
    bars = tuple(dataset.bars[index] for index in indices)
    return MarketDataSet(
        dataset.version, dataset.zone, bars, dataset.timeframe, dataset.calendar
    )


def _select_feature_values(
    feature_values: Mapping[str, Sequence[float | None]] | None,
    indices: Sequence[int],
) -> Mapping[str, Sequence[float | None]] | None:
    if feature_values is None:
        return None
    return {
        name: tuple(values[index] for index in indices)
        for name, values in feature_values.items()
    }


def _compare(
    equity: Sequence[float], benchmark: BenchmarkData | None, *, periods_per_year: float
) -> BenchmarkComparison | None:
    if benchmark is None:
        return None
    return compare_benchmarks(
        equity,
        benchmark.qqq_prices,
        benchmark.nasdaq_prices,
        qqq_distributions=benchmark.qqq_distributions,
        nasdaq_distributions=benchmark.nasdaq_distributions,
        periods_per_year=periods_per_year,
    )
