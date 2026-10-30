"""Read-only costed precommit guard for GPT-guided strategy mutations.

Compare exact executed fills, using the SAME canonical strategy engine, market,
cost model and starting equity as the real evaluation pipeline. An IR/semantic
hash difference alone is never proof of a changed execution.

This guard does not use sealed OOS or approve/promote any strategy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.data.contracts import DataZone, MarketDataSet
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from experiments.candidate_generator import Candidate
from experiments.identity import semantic_strategy_hash
from orchestration.evaluation_runner import _market_feature_inputs
from orchestration.pipeline import GenerationPipeline
from strategy_ir.schema import StrategyIR


def require_costed_execution_change(
    *,
    parent: StrategyIR,
    candidates: Sequence[Candidate],
    dataset: MarketDataSet,
) -> tuple[str, ...]:
    """Fail before any checkpoint CAS if an experiment has no executable change.

    All candidates must contain at least one fill and have a different canonical
    fill trace from the same-source control. Same-count fills are allowed when
    their timestamp, side, price, quantity, notional or costs differ. Conditions
    that merely alter IR metadata or do not bind on observed bars are rejected.
    This is a *development* identity check, not an independence/alpha test.
    """
    if dataset.zone != DataZone.DEVELOPMENT:
        raise PermissionError("STRICT_EXECUTION_REQUIRES_DEVELOPMENT_ONLY")
    if not candidates:
        raise ValueError("STRICT_EXECUTION_NO_CANDIDATES")
    engine = BacktestEngine()
    feature_specs = {s.name: s for s in research_feature_specs()}
    feature_inputs = _market_feature_inputs(dataset)
    cost_model = GenerationPipeline().cost_model

    def fills(strategy: StrategyIR):
        result = engine.run(
            BacktestRequest(
                run_id="guided-strict-precommit",
                strategy_hash=semantic_strategy_hash(strategy),
                dataset=dataset,
                initial_cash=100_000.0,
                strategy=strategy,
                cost_model=cost_model,
                feature_specs=feature_specs,
                feature_inputs=feature_inputs,
            )
        )
        if result.exit_status != "SUCCEEDED" or result.data_hash != dataset.dataset_hash:
            raise ValueError("STRICT_EXECUTION_REPLAY_FAILED")
        return result.trades

    try:
        control_trades = fills(parent)
    except Exception as exc:
        raise ValueError("STRICT_EXECUTION_PARENT_REPLAY_UNVERIFIED") from exc

    execution_hashes: list[str] = []
    for candidate in candidates:
        try:
            actual_trades = fills(candidate.strategy)
        except Exception as exc:
            raise ValueError("STRICT_EXECUTION_CHILD_REPLAY_UNVERIFIED") from exc
        if not actual_trades:
            raise ValueError("STRICT_EXECUTION_NO_TRADES: zero executable fills in candidate")
        if actual_trades == control_trades:
            raise ValueError(
                "STRICT_EXECUTION_UNCHANGED: IR changed but canonical costed fills match parent"
            )
        trace_hash = content_hash(tuple(asdict(trade) for trade in actual_trades))
        if trace_hash in execution_hashes:
            raise ValueError("STRICT_EXECUTION_DUPLICATE_IN_BATCH")
        execution_hashes.append(trace_hash)
    return tuple(execution_hashes)
