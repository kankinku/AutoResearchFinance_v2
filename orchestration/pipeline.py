from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

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
    group_holdout_return_scores,
    probability_backtest_overfitting,
    robust_statistics,
)
from evaluation.selector import FunnelConfig, FunnelInput, FunnelResult, select_candidate
from evaluation.yearly import summarize_yearly_performance
from experiments.candidate_generator import Candidate, generate_candidates
from experiments.deduplicator import deduplicate_candidates
from experiments.identity import semantic_strategy_hash
from memory.knowledge import extract_knowledge
from mutation.engine import MutationOperation
from mutation.parameter import BayesianObservation, ParameterDomain
from orchestration.generation import CANONICAL_STAGES
from orchestration.train_only import TrainOnlyFold, TrainOnlySelectionReport
from strategy_ir.schema import StrategyIR


@dataclass(frozen=True)
class GenerationPipelineResult:
    stages: tuple[str, ...]
    candidates: tuple[Candidate, ...]
    funnel: tuple[FunnelResult, ...]
    knowledge: dict[str, object]
    train_only_selection: TrainOnlySelectionReport | None = None
    multiple_testing_trials: int = 1
    duplicate_skipped: int = 0


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
        prior_trials: int = 0,
        excluded_semantic_hashes: tuple[str, ...] = (),
    ) -> GenerationPipelineResult:
        if prior_trials < 0:
            raise ValueError("prior_trials must be nonnegative")
        if DataZone(dataset.zone) is not DataZone.DEVELOPMENT:
            raise PermissionError("generation research requires development market data")
        if (
            external_series is not None
            and DataZone(external_series.zone) is not DataZone.DEVELOPMENT
        ):
            raise PermissionError("generation research requires development series data")

        generated = generate_candidates(
            parent,
            operations,
            domains,
            method=method,
            count=count,
            seed=seed,
            observations=observations,
        )
        deduplicated = deduplicate_candidates(list(generated), semantic=True).unique
        candidates = tuple(
            candidate
            for candidate in deduplicated
            if semantic_strategy_hash(candidate.strategy) not in excluded_semantic_hashes
        )
        duplicate_skipped = len(deduplicated) - len(candidates)
        multiple_testing_trials = max(1, len(candidates) + prior_trials)
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
                pbo = probability_backtest_overfitting(tuple(item.returns for item in evaluated))
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
                resampling_scores = group_holdout_return_scores(item.returns)
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
                trials=multiple_testing_trials,
                observations=len(item.returns),
                complexity=complexity,
                pbo=pbo,
                sample_returns=item.returns,
                annualization_factor=periods_per_year(dataset),
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
        selection = self._select_train_only(
            candidates,
            dataset,
            parent=parent,
            operations=operations,
            domains=domains,
            count=count,
            seed=seed,
            feature_values=feature_values,
            feature_inputs=feature_inputs,
            external_series=external_series,
            method=method,
            prior_observations_supplied=bool(observations),
            excluded_semantic_hashes=excluded_semantic_hashes,
        )
        return GenerationPipelineResult(
            CANONICAL_STAGES,
            candidates,
            tuple(results),
            knowledge,
            selection,
            multiple_testing_trials,
            duplicate_skipped,
        )

    def _select_train_only(
        self,
        candidates: tuple[Candidate, ...],
        dataset: MarketDataSet,
        *,
        parent: StrategyIR,
        operations: tuple[MutationOperation, ...],
        domains: tuple[ParameterDomain, ...],
        count: int,
        seed: int,
        method: str,
        prior_observations_supplied: bool,
        excluded_semantic_hashes: tuple[str, ...],
        feature_values: Mapping[str, Sequence[float | None]] | None,
        feature_inputs: Mapping[str, Sequence[float | None]] | None,
        external_series: SeriesDataSet | None,
    ) -> TrainOnlySelectionReport:
        """Choose a candidate from training returns, then freeze before test.

        Precomputed and external features cannot be proven point-in-time safe by
        this layer, so only native, causal price-indicator strategies are admitted.
        The report does not qualify an experiment for sealed-OOS promotion.
        """
        if not candidates:
            return TrainOnlySelectionReport("INSUFFICIENT_CANDIDATES")
        if method == "bayesian" and prior_observations_supplied:
            return TrainOnlySelectionReport(
                "UNVERIFIED_UPSTREAM_OPTIMIZATION",
                reason=(
                    "prior Bayesian observations lack fold-specific training-window "
                    "provenance and may include later market information"
                ),
            )
        # Market OHLCV input arrays and benchmark series are unused when all
        # candidates use native indicators exclusively; do not block those.
        if feature_values is not None or any(
            candidate.strategy.features for candidate in candidates
        ):
            return TrainOnlySelectionReport(
                "UNSUPPORTED_UNVERIFIED_FEATURES",
                reason="point-in-time external feature provenance is unverified",
            )
        times = tuple(sorted({bar.timestamp for bar in dataset.bars}))
        splits = walk_forward_splits(
            tuple(range(len(times))),
            train_size=max(1, len(times) // 2),
            test_size=max(1, len(times) // 4),
            step=max(1, len(times) // 4),
        )
        if not splits:
            return TrainOnlySelectionReport("INSUFFICIENT_HISTORY")
        evidence: list[TrainOnlyFold] = []
        for fold_id, (train_indices, test_indices) in enumerate(splits):
            train_begin, train_end = times[train_indices[0]], times[train_indices[-1]]
            test_begin, test_end = times[test_indices[0]], times[test_indices[-1]]
            training_indices = tuple(
                index
                for index, bar in enumerate(dataset.bars)
                if train_begin <= bar.timestamp <= train_end
            )
            train_data = _select_dataset(dataset, training_indices)
            # Do not share generated candidates between folds. Candidate
            # mutations and parameter draws are recomputed after each fold's
            # training dataset has been sealed. This generator is data-blind;
            # source hypotheses from the parent remain unverified upstream.
            generation_seed = seed + fold_id
            fold_generated = generate_candidates(
                parent,
                operations,
                domains,
                method=method,
                count=count,
                seed=generation_seed,
                observations=None,
            )
            fold_candidates = tuple(
                candidate
                for candidate in deduplicate_candidates(list(fold_generated), semantic=True).unique
                if semantic_strategy_hash(candidate.strategy) not in excluded_semantic_hashes
            )
            if not fold_candidates:
                return TrainOnlySelectionReport("INSUFFICIENT_CANDIDATES")
            scored = tuple(
                (self._evaluate(candidate, train_data, f"select-train-{fold_id}")[0], candidate)
                for candidate in fold_candidates
            )
            # Deterministic pre-test tie-breaker; underperformance in the test
            # period must not influence the selected strategy or training score.
            train_metrics, chosen = sorted(
                scored,
                key=lambda item: (-item[0].total_return, item[1].candidate_hash),
            )[0]
            prefix_indices = tuple(
                index for index, bar in enumerate(dataset.bars) if bar.timestamp <= test_end
            )
            prefix_data = _select_dataset(dataset, prefix_indices)
            test_metrics, _, _ = self._evaluate(
                chosen,
                prefix_data,
                f"select-test-{fold_id}",
                signal_start_at=test_begin,
            )
            evidence.append(
                TrainOnlyFold(
                    fold=fold_id,
                    selected_candidate_hash=chosen.candidate_hash,
                    candidate_count=len(fold_candidates),
                    train_dataset_hash=train_data.dataset_hash,
                    generation_seed=generation_seed,
                    generated_candidate_hashes=tuple(
                        candidate.candidate_hash for candidate in fold_candidates
                    ),
                    candidate_generation_cutoff_at=train_end.isoformat(),
                    train_total_return=train_metrics.total_return,
                    train_end_at=train_end.isoformat(),
                    test_start_at=test_begin.isoformat(),
                    test_end_at=test_end.isoformat(),
                    test_total_return=test_metrics.total_return,
                    test_trade_count=test_metrics.trade_count,
                )
            )
        return TrainOnlySelectionReport(
            "EVALUATED", tuple(evidence), sum(fold.candidate_count for fold in evidence)
        )

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
                index for index, bar in enumerate(dataset.bars) if bar.timestamp in test_timestamps
            )
            test_dataset = _select_dataset(dataset, test_bar_indices)
            # Include only historical training/warmup bars and this fold's test
            # window. The backtest engine forbids orders from the warmup bars.
            prefix_indices = tuple(
                index
                for index, bar in enumerate(dataset.bars)
                if bar.timestamp <= timestamps[test_indices[-1]]
            )
            prefix_dataset = _select_dataset(dataset, prefix_indices)
            prefix_feature_values = _select_feature_values(feature_values, prefix_indices)
            prefix_feature_inputs = _select_feature_values(feature_inputs, prefix_indices)
            metrics, _, equity = self._evaluate(
                candidate,
                prefix_dataset,
                f"validation-{fold_index}",
                prefix_feature_values,
                feature_specs,
                prefix_feature_inputs,
                external_series,
                signal_start_at=timestamps[test_indices[0]],
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
            target_passed = comparison is not None and (
                funnel.min_qqq_cagr_delta is None
                or comparison.qqq_cagr_delta >= funnel.min_qqq_cagr_delta
            )
            return_passed = metrics.total_return >= funnel.min_full_return
            trade_passed = metrics.trade_count >= funnel.min_full_trades
            failure_checks = [
                ("trade_count", not trade_passed),
                ("total_return", not return_passed),
            ]
            if funnel.min_qqq_cagr_delta is not None:
                failure_checks.append(("qqq_cagr_delta", not target_passed))
            passed = (
                trade_passed
                and return_passed
                and (target_passed if funnel.min_qqq_cagr_delta is not None else True)
            )
            evidence.append(
                {
                    "fold": fold_index,
                    "method": "temporal_holdout",
                    "selection_applied": False,
                    "warmup_history_used": True,
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
                        reason for reason, condition in failure_checks if condition
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
        signal_start_at: datetime | None = None,
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
                signal_start_at=signal_start_at,
            )
        )
        evaluation_dataset = dataset
        trades = backtest.trades
        equity = backtest.equity_curve
        if signal_start_at is not None:
            timestamps = equity_timestamps(dataset, len(equity))
            equity = tuple(
                value
                for timestamp, value in zip(timestamps, equity, strict=True)
                if timestamp >= signal_start_at
            )
            evaluation_dataset = _select_dataset(
                dataset,
                tuple(
                    index
                    for index, bar in enumerate(dataset.bars)
                    if bar.timestamp >= signal_start_at
                ),
            )
            trades = tuple(
                trade
                for trade in trades
                if datetime.fromisoformat(trade.timestamp) >= signal_start_at
            )
        pnls = _closed_trade_pnls(trades)
        metrics = calculate_metrics(
            equity,
            pnls,
            periods_per_year=periods_per_year(evaluation_dataset),
            turnover=sum(trade.notional for trade in trades),
            exposure=_capital_exposure(evaluation_dataset, equity, trades),
        )
        return metrics, trades, equity


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
        dataset.version,
        dataset.zone,
        tuple(bars),
        dataset.timeframe,
        dataset.calendar,
        dataset.provenance,
    )


def _timestamp_count(dataset: MarketDataSet) -> int:
    return len({bar.timestamp for bar in dataset.bars})


def _capital_exposure(
    dataset: MarketDataSet,
    equity_curve: tuple[float, ...],
    trades: tuple[Trade, ...],
) -> float:
    """Average close-to-close fraction of equity held in long positions.

    Orders fill at each bar's open, so holdings after that day's fills are
    marked to the latest available *close*. For asynchronous multi-symbol bars,
    use each symbol's most recent close; never count a completed round-trip as
    a proxy for capital at risk.
    """
    timestamps = equity_timestamps(dataset, len(equity_curve))
    if not timestamps:
        return 0.0
    prices_by_time: dict[str, dict[str, float]] = {}
    for bar in dataset.bars:
        prices_by_time.setdefault(bar.timestamp.isoformat(), {})[bar.symbol] = bar.close
    trades_by_time: dict[str, list[Trade]] = {}
    for trade in trades:
        trades_by_time.setdefault(trade.timestamp, []).append(trade)
    if set(trades_by_time) - set(prices_by_time):
        raise ValueError("trade timestamp is not present in market data")

    prices: dict[str, float] = {}
    quantities: dict[str, float] = {}
    fractions: list[float] = []
    for timestamp, equity in zip(timestamps, equity_curve, strict=True):
        key = timestamp.isoformat()
        prices.update(prices_by_time[key])
        for trade in trades_by_time.get(key, ()):
            if trade.symbol not in prices:
                raise ValueError("trade symbol is absent from market data")
            if trade.side == "buy":
                quantities[trade.symbol] = quantities.get(trade.symbol, 0.0) + trade.quantity
            elif trade.side == "sell":
                remaining = quantities.get(trade.symbol, 0.0) - trade.quantity
                if remaining < -1e-8:
                    raise ValueError("sell exceeds held quantity")
                quantities[trade.symbol] = max(remaining, 0.0)
            else:
                raise ValueError("unsupported trade side")
        if equity <= 0:
            raise ValueError("equity must be positive for exposure")
        invested = sum(quantity * prices[symbol] for symbol, quantity in quantities.items())
        fractions.append(invested / equity)
    return sum(fractions) / len(fractions)


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
        dataset.version,
        dataset.zone,
        bars,
        dataset.timeframe,
        dataset.calendar,
        dataset.provenance,
    )


def _select_feature_values(
    feature_values: Mapping[str, Sequence[float | None]] | None,
    indices: Sequence[int],
) -> Mapping[str, Sequence[float | None]] | None:
    if feature_values is None:
        return None
    return {
        name: tuple(values[index] for index in indices) for name, values in feature_values.items()
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
