"""D06: safe time alignment and independent per-asset StrategyIR development runs.

This does not compile cross-sectional strategies or create a combined portfolio.
Each existing typed, already-gated single-symbol compiler runs separately on a
strictly common US-equity session grid, with no ffill, OOS access or orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from math import isfinite
from typing import Literal
from zoneinfo import ZoneInfo

from core.data.contracts import Bar, DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    CompiledAlgorithmPlan,
    compile_algorithm_plan,
    evaluate_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog

_NY = ZoneInfo("America/New_York")
_ALLOWED = frozenset({"QQQ", "SPY", "IWM", "DIA", "VTI", "EFA", "TLT", "GLD"})


class MultiAssetResearchError(ValueError):
    """Reject potentially stale or misaligned multi-symbol inputs."""


@dataclass(frozen=True)
class AlignedResearchMarket:
    symbols: tuple[str, ...]
    session_dates: tuple[date, ...]
    decision_known_at_utc: tuple[datetime, ...]
    execution_next_open_at_utc: tuple[datetime | None, ...]
    symbol_datasets: tuple[tuple[str, MarketDataSet], ...]
    input_dataset_hash: str
    alignment_hash: str
    status: Literal["RESEARCH_MULTI_ASSET_ALIGNED_NON_PIT"] = (
        "RESEARCH_MULTI_ASSET_ALIGNED_NON_PIT"
    )
    broker_executable: Literal[False] = False
    sealed_oos_approved: Literal[False] = False


@dataclass(frozen=True)
class ParallelCompiledPlan:
    alignment: AlignedResearchMarket
    plan_hash: str
    compiled_by_symbol: tuple[tuple[str, CompiledAlgorithmPlan], ...]
    status: Literal["INDEPENDENT_SYMBOL_STRATEGY_IR_DEVELOPMENT_ONLY"] = (
        "INDEPENDENT_SYMBOL_STRATEGY_IR_DEVELOPMENT_ONLY"
    )
    broker_executable: Literal[False] = False
    sealed_oos_approved: Literal[False] = False


@dataclass(frozen=True)
class SymbolRun:
    symbol: str
    strategy_hash: str
    dataset_hash: str
    replay_hash: str
    initial_cash: float
    final_equity: float
    equity_hash: str
    trades_count: int
    transaction_costs_paid: float
    status: Literal["NON_PIT_DEVELOPMENT_RESULT"] = "NON_PIT_DEVELOPMENT_RESULT"
    broker_executable: Literal[False] = False


@dataclass(frozen=True)
class ParallelStudy:
    study_dataset_hash: str
    alignment_hash: str
    plan_hash: str
    symbol_results: tuple[SymbolRun, ...]
    study_hash: str
    status: Literal["MULTI_ASSET_DEVELOPMENT_COMPARISON_ONLY"] = (
        "MULTI_ASSET_DEVELOPMENT_COMPARISON_ONLY"
    )
    portfolio_pnl_approved: Literal[False] = False
    independent_oos_approved: Literal[False] = False
    broker_executable: Literal[False] = False


def align_parallel_market(
    market: MarketDataSet, *,
    symbols: tuple[str, ...] | None = None,
) -> AlignedResearchMarket:
    """Require exact US trading-date sets; refuse mismatched/missing bar sessions.

    A daily close timestamp must be no earlier than 16:00 New York local.
    Early close sessions are excluded pending an independently verified calendar.
    The common close is the MAX of bar timestamps for that exchange date.
    A bar's signal can be acted on no earlier than the next shared 09:30 open;
    neither that next bar nor a future close is available at decision time.
    """
    if not isinstance(market, MarketDataSet):
        raise MultiAssetResearchError("typed MarketDataSet is required")
    if (market.zone != DataZone.DEVELOPMENT
            or market.timeframe != "1d" or market.calendar != "us_equities"):
        raise MultiAssetResearchError("only development US-equity daily histories allowed")
    present = tuple(sorted({bar.symbol for bar in market.bars}))
    if symbols is None:
        requested = present
    else:
        if (not isinstance(symbols, tuple)
                or any(not isinstance(value, str) for value in symbols)):
            raise MultiAssetResearchError("symbols must be a tuple of instrument IDs")
        requested = tuple(sorted(symbols))
        if len(set(requested)) != len(requested) or requested != present:
            raise MultiAssetResearchError("symbols must match the complete market universe")
    if not 2 <= len(requested) <= 8 or set(requested) - _ALLOWED:
        raise MultiAssetResearchError("research supports only 2-8 allowlisted US ETFs")
    grouped: dict[str, dict[date, Bar]] = {symbol: {} for symbol in requested}
    for bar in market.bars:
        local = bar.timestamp.astimezone(_NY)
        session = local.date()
        if session.weekday() >= 5:
            raise MultiAssetResearchError("unreviewed weekend session is not eligible")
        if not time(16, 0) <= local.timetz().replace(tzinfo=None) < time(23, 0):
            raise MultiAssetResearchError("daily bar must be complete after NYSE 16:00 close")
        if session in grouped[bar.symbol]:
            raise MultiAssetResearchError("duplicate exchange session for symbol")
        grouped[bar.symbol][session] = bar
    dates = tuple(sorted(grouped[requested[0]]))
    if not 2 <= len(dates) <= 10_000:
        raise MultiAssetResearchError("bounded shared sessions require 2-10000 bars")
    for symbol in requested[1:]:
        if tuple(sorted(grouped[symbol])) != dates:
            raise MultiAssetResearchError(
                "missing or extra symbol session; no forward-fill allowed"
            )
    # Use observation's completed timestamp, not the calendar date as availability.
    known: list[datetime] = []
    future_open: list[datetime | None] = []
    for i, session in enumerate(dates):
        latest = max(
            grouped[symbol][session].timestamp.astimezone(timezone.utc)
            for symbol in requested
        )
        known.append(latest)
        if i + 1 == len(dates):
            future_open.append(None)
            continue
        next_open = datetime.combine(dates[i + 1], time(9, 30), tzinfo=_NY).astimezone(
            timezone.utc
        )
        if latest >= next_open:
            raise MultiAssetResearchError("next session open precedes data completion")
        future_open.append(next_open)
    by_symbol: list[tuple[str, MarketDataSet]] = []
    for symbol in requested:
        bars = tuple(grouped[symbol][session] for session in dates)
        submarket = MarketDataSet(
            version=market.version + ":" + symbol,
            zone=DataZone.DEVELOPMENT,
            bars=bars,
            timeframe=market.timeframe,
            calendar=market.calendar,
            provenance=market.provenance,
        )
        by_symbol.append((symbol, submarket))
    proof = {
        "schema": "strict-common-exchange-sessions-v1",
        "input_market_hash": market.dataset_hash,
        "symbols": requested,
        "sessions": [d.isoformat() for d in dates],
        "completion_utc": [t.isoformat() for t in known],
        "next_open_utc": [t.isoformat() if t is not None else None for t in future_open],
        "symbol_dataset_hashes": [(s, d.dataset_hash) for s, d in by_symbol],
        "interpolation": "FORBIDDEN",
        "independent_pit": False,
    }
    return AlignedResearchMarket(
        symbols=requested,
        session_dates=dates,
        decision_known_at_utc=tuple(known),
        execution_next_open_at_utc=tuple(future_open),
        symbol_datasets=tuple(by_symbol),
        input_dataset_hash=market.dataset_hash,
        alignment_hash=content_hash(proof),
    )


def compile_parallel_plan(
    catalog: ResearchCatalog, plan: AlgorithmPlan, market: MarketDataSet,
) -> ParallelCompiledPlan:
    """Compile unchanged typed AlgorithmPlan independently per market instrument."""
    alignment = align_parallel_market(market)
    compiled = tuple(
        (symbol, compile_algorithm_plan(catalog, plan, segment))
        for symbol, segment in alignment.symbol_datasets
    )
    plan_hash = content_hash(plan.model_dump(mode="json"))
    if any(piece.plan_hash != plan_hash for _, piece in compiled):
        raise MultiAssetResearchError("per-asset AlgorithmPlan changed unexpectedly")
    return ParallelCompiledPlan(
        alignment=alignment, plan_hash=plan_hash, compiled_by_symbol=compiled,
    )


def evaluate_parallel_plan(
    catalog: ResearchCatalog, compiled: ParallelCompiledPlan,
    market: MarketDataSet, *, per_symbol_initial_cash: float = 10_000.0,
) -> ParallelStudy:
    """Recheck frozen study/alignment, then compare *separate* costed runs.

    Cash is NOT shared across instruments; no portfolio PnL or allocation is
    inferred from these independent, equal-notional development experiments.
    """
    if (type(per_symbol_initial_cash) not in (float, int)
            or not isfinite(per_symbol_initial_cash)
            or per_symbol_initial_cash <= 0):
        raise MultiAssetResearchError("cash must be finite positive independent notional")
    verified = align_parallel_market(market)
    if compiled.alignment != verified:
        raise MultiAssetResearchError("alignment changed or proof hash mismatch")
    if (compiled.status != "INDEPENDENT_SYMBOL_STRATEGY_IR_DEVELOPMENT_ONLY"
            or compiled.broker_executable is not False
            or compiled.sealed_oos_approved is not False
            or compiled.plan_hash != content_hash(
                compiled.compiled_by_symbol[0][1].plan.model_dump(mode="json")
            )):
        raise MultiAssetResearchError("frozen plan identity or permissions changed")
    if tuple(symbol for symbol, _ in compiled.compiled_by_symbol) != verified.symbols:
        raise MultiAssetResearchError("compiled symbol universe mismatch")
    observations: list[SymbolRun] = []
    for (symbol, frozen), (_, segment) in zip(
        compiled.compiled_by_symbol, verified.symbol_datasets, strict=True
    ):
        if frozen.plan_hash != compiled.plan_hash:
            raise MultiAssetResearchError("plan hashes differ between assets")
        # The canonical single-symbol verifier independently replays the entire IR.
        result = evaluate_algorithm_plan(
            catalog, frozen, segment, initial_cash=float(per_symbol_initial_cash),
        )
        observations.append(SymbolRun(
            symbol=symbol,
            strategy_hash=result.strategy_hash,
            dataset_hash=result.dataset_hash,
            replay_hash=result.replay_hash,
            initial_cash=result.initial_cash,
            final_equity=result.final_equity,
            equity_hash=result.equity_hash,
            trades_count=result.trades_count,
            transaction_costs_paid=result.total_paid_costs,
        ))
    identity = {
        "schema": "parallel-algorithm-plan-v1",
        "market_hash": market.dataset_hash,
        "alignment_hash": verified.alignment_hash,
        "plan_hash": compiled.plan_hash,
        "independent_symbol_results": [
            (o.symbol, o.dataset_hash, o.strategy_hash, o.replay_hash,
             o.equity_hash, o.trades_count, o.transaction_costs_paid)
            for o in observations
        ],
        "no_cross_symbol_portfolio_pnl": True,
    }
    return ParallelStudy(
        study_dataset_hash=market.dataset_hash,
        alignment_hash=verified.alignment_hash,
        plan_hash=compiled.plan_hash,
        symbol_results=tuple(observations),
        study_hash=content_hash(identity),
    )
