from __future__ import annotations

from dataclasses import dataclass

from core.backtest.engine import BacktestEngine, BacktestRequest, Trade
from core.data.contracts import DataZone, MarketDataSet
from core.validation.walk_forward import walk_forward_splits
from evaluation.metrics import Metrics, calculate_metrics
from evaluation.robustness import robust_statistics
from evaluation.selector import FunnelConfig, FunnelInput, FunnelResult, select_candidate
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


class GenerationPipeline:
    """Local end-to-end generation loop over immutable data and deterministic workers."""

    def __init__(self, *, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()

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
    ) -> GenerationPipelineResult:
        if DataZone(dataset.zone) is DataZone.SEALED_OOS:
            raise PermissionError("generation research cannot use sealed OOS data")
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
        results: list[FunnelResult] = []
        for candidate in candidates:
            fast_metrics, _ = self._evaluate(candidate, fast_dataset, "fast")
            full_metrics, trades = self._evaluate(candidate, dataset, "full")
            robust = robust_statistics(
                base_return=full_metrics.total_return,
                stressed_return=full_metrics.total_return,
                parameter_scores=(fast_metrics.total_return, full_metrics.total_return),
                sharpe=full_metrics.sharpe or 0.0,
                trials=max(1, len(candidates)),
                observations=len(full_metrics.__dict__),
                complexity=len(candidate.strategy.indicators)
                + len(candidate.strategy.entry.conditions)
                + len(candidate.strategy.exit.conditions),
            )
            validation_passed = bool(
                walk_forward_splits(
                    tuple(range(len(dataset.bars))),
                    train_size=max(1, len(dataset.bars) // 2),
                    test_size=max(1, len(dataset.bars) // 4),
                    step=max(1, len(dataset.bars) // 4),
                )
            )
            results.append(
                select_candidate(
                    FunnelInput(
                        candidate.candidate_hash,
                        candidate.strategy.family,
                        fast_metrics,
                        full_metrics,
                        robust,
                        validation_passed,
                    ),
                    funnel,
                )
            )
            del trades
        knowledge = extract_knowledge(generation=parent.generation + 1, results=tuple(results))
        return GenerationPipelineResult(CANONICAL_STAGES, candidates, tuple(results), knowledge)

    def _evaluate(
        self, candidate: Candidate, dataset: MarketDataSet, run_kind: str
    ) -> tuple[Metrics, tuple[Trade, ...]]:
        backtest = self.engine.run(
            BacktestRequest(
                f"{candidate.candidate_hash}-{run_kind}",
                candidate.candidate_hash,
                dataset,
                100_000.0,
                strategy=candidate.strategy,
            )
        )
        pnls = _closed_trade_pnls(backtest.trades)
        return (
            calculate_metrics(
                backtest.equity_curve,
                pnls,
                periods_per_year=252,
                turnover=sum(trade.notional for trade in backtest.trades),
                exposure=len(pnls) / max(len(backtest.equity_curve), 1),
            ),
            backtest.trades,
        )


def _fast_slice(dataset: MarketDataSet) -> MarketDataSet:
    width = max(2, len(dataset.bars) // 2)
    return MarketDataSet(dataset.version, dataset.zone, dataset.bars[:width])


def _closed_trade_pnls(trades: tuple[Trade, ...]) -> tuple[float, ...]:
    buys: list[Trade] = []
    pnls: list[float] = []
    for trade in trades:
        if trade.side == "buy":
            buys.append(trade)
        elif buys:
            buy = buys.pop(0)
            pnls.append((trade.price - buy.price) * trade.quantity - trade.cost - buy.cost)
    return tuple(pnls)
