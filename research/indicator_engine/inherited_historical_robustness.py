"""Read-only annual robustness from a *fully audit-replayed* inherited StrategyIR.

Never trust a claimed parent, raw StrategyIR, or arbitrarily recomputed vector.
The supplied parent must reproduce its canonical DEVELOPMENT audit and measured
full-period equity. Slicing verified causal vectors through each annual end
preserves exact counted-parent feature lineage without opening future data.
These are EX-POST historical diagnostics, not OOS or model selection evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from math import isfinite
from typing import Any, Literal, cast

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from research.indicator_engine.bridge import ResearchSignalReplay
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.development_benchmark import (
    compare_qqq_development_benchmarks,
)
from research.indicator_engine.historical_robustness import HistoricalPeriod
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.strategy_adapter import (
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)


@dataclass(frozen=True)
class InheritedRobustnessReport:
    strategy_hash: str
    source_evidence_hash: str
    full_audit_hash: str
    development_hash: str
    cutoff_date: str
    periods: tuple[HistoricalPeriod, ...]
    report_hash: str
    selection_scope: Literal["HISTORICALLY_EXPOSED_REPLAY_NOT_OOS"] = (
        "HISTORICALLY_EXPOSED_REPLAY_NOT_OOS"
    )
    status: Literal["INHERITED_IR_EX_POST_DEVELOPMENT_ONLY"] = (
        "INHERITED_IR_EX_POST_DEVELOPMENT_ONLY"
    )
    independent_oos_approved: Literal[False] = False
    candidate_promotable: Literal[False] = False
    broker_executable: Literal[False] = False


def _checked_source(
    compiled: CompiledAcademicStrategy,
    evidence: Mapping[str, Any],
    market: MarketDataSet,
) -> str:
    if (
        evidence.get("dataset_hash") != market.dataset_hash
        or evidence.get("strategy_hash") != compiled.strategy_hash
        or evidence.get("broker_executable") is not False
        or evidence.get("independent_oos_approved") is not False
        or not isinstance(evidence.get("audit_hash"), str)
    ):
        raise ResearchCatalogError("inherited counted strategy evidence identity mismatch")
    source_hash = evidence.get("evidence_hash")
    if (
        not isinstance(source_hash, str)
        or len(source_hash) != 64
        or any(char not in "0123456789abcdef" for char in source_hash)
    ):
        raise ResearchCatalogError("source evidence hash missing or invalid")
    # Canonical audit binds exact full-period vectors, order times, costs,
    # decisions and net PnL. This must be validated against the historical
    # ledger; reported gain alone is insufficient (G64 has a lineage replay).
    audited = audit_inherited_decisions(compiled, market)
    measured = evidence.get("measured_final_equity")
    measured_float = (
        float(cast(int | float, measured))
        if type(measured) in (int, float) else float("nan")
    )
    metrics = evidence.get("metrics")
    if (
        audited.trace_hash != evidence["audit_hash"]
        or type(measured) not in (int, float)
        or not isfinite(measured_float)
        or abs(audited.evaluation.final_equity - measured_float) > 1e-6
        or not isinstance(metrics, dict)
        or type(metrics.get("trade_count")) is not int
        or len(audited.round_trips) != metrics["trade_count"]
    ):
        raise ResearchCatalogError("inherited full-period audit / economic replay mismatch")
    return source_hash


def _prefix_replay(
    compiled: CompiledAcademicStrategy,
    market: MarketDataSet,
    end: int,
) -> tuple[CompiledAcademicStrategy, MarketDataSet]:
    if end < 3 or end > len(market.bars):
        raise ResearchCatalogError("invalid bounded historical replay prefix")
    prefix = MarketDataSet(
        market.version + f"-inherited-prefix-{end}",
        DataZone.DEVELOPMENT,
        market.bars[:end],
        market.timeframe,
        market.calendar,
        market.provenance,
    )
    values = {name: tuple(series[:end]) for name, series in compiled.feature_values.items()}
    if set(values) != set(compiled.strategy.features) or any(
        len(series) != end for series in values.values()
    ):
        raise ResearchCatalogError("inherited feature replay vector coverage mismatch")
    observations = tuple((alias, values[alias]) for alias in sorted(values))
    stamps = tuple(bar.timestamp for bar in prefix.bars)
    next_stamp = stamps[1:] + (None,)
    hypothesis = content_hash({
        "schema": "inherited-historical-prefix-v1",
        "source_strategy": compiled.strategy_hash,
        "prefix_dataset": prefix.dataset_hash,
        "signal_hash": content_hash(observations),
    })
    replay_body = {
        "hypothesis": hypothesis,
        "dataset": prefix.dataset_hash,
        "signals": observations,
        "decision_timestamps": [t.isoformat() for t in stamps],
        "earliest_next_bar": [t.isoformat() if t else None for t in next_stamp],
        "research_only": True,
    }
    replay = ResearchSignalReplay(
        hypothesis_hash=hypothesis,
        data_hash=prefix.dataset_hash,
        signals=observations,
        timestamps=stamps,
        execution_not_before=next_stamp,
        entry_regime_observations=0,
        replay_hash=content_hash(replay_body),
    )
    return replace(
        compiled,
        hypothesis_hash=hypothesis,
        dataset_hash=prefix.dataset_hash,
        replay=replay,
        feature_values=values,
    ), prefix


def evaluate_inherited_historical_robustness(
    compiled: CompiledAcademicStrategy,
    counted_evidence: Mapping[str, Any],
    market: MarketDataSet,
    *,
    years: Sequence[int],
    last_development_date: date,
    initial_cash: float = 10_000.0,
    min_period_bars: int = 30,
) -> InheritedRobustnessReport:
    """Run fixed inherited StrategyIR per year, with past bars as CASH-ONLY warmup.

    The caller must FIRST load counted_evidence from a hash-chain validated
    ledger (ideally an isolated copy of AcademicCycleService), then reconstruct
    the exact parent using the service's checked lineage/S7 replay mechanism.
    This function itself validates the canonical full-period audit and cannot
    certify the ledger's external authenticity.
    """
    if (
        market.zone != DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or len(market.bars) < 60
        or any(bar.symbol != "QQQ" for bar in market.bars)
        or compiled.dataset_hash != market.dataset_hash
    ):
        raise ResearchCatalogError("inherited replay requires matching QQQ DEVELOPMENT data")
    if (
        not isinstance(last_development_date, date)
        or isinstance(last_development_date, datetime)
        or market.bars[-1].timestamp.date() > last_development_date
    ):
        raise ResearchCatalogError("inherited replay rejects data after development cutoff")
    if any(
        a.timestamp >= b.timestamp
        for a, b in zip(market.bars, market.bars[1:], strict=False)
    ):
        raise ResearchCatalogError("unordered inherited research bar timestamps")
    if (
        not years
        or any(type(year) is not int for year in years)
        or tuple(years) != tuple(sorted(set(years)))
        or type(min_period_bars) is not int
        or min_period_bars < 3
        or type(initial_cash) not in (float, int)
        or not isfinite(initial_cash)
        or initial_cash <= 0
    ):
        raise ResearchCatalogError("invalid inherited historical study specification")
    if initial_cash != 10_000.0:
        # The authenticated counted campaign used 10k. A different capital
        # basis would invalidate its replay parity proof and evidence metrics.
        raise ResearchCatalogError("source campaign capital basis is fixed to 10000")
    source_hash = _checked_source(compiled, counted_evidence, market)
    years_seen = {bar.timestamp.year for bar in market.bars}
    periods = []
    for year in years:
        if year not in years_seen or year > last_development_date.year:
            raise ResearchCatalogError("missing or future inherited study year")
        left = next(i for i, bar in enumerate(market.bars) if bar.timestamp.year == year)
        right = next(
            (i for i, bar in enumerate(market.bars) if bar.timestamp.year > year),
            len(market.bars),
        )
        if left < 1 or right - left < min_period_bars:
            raise ResearchCatalogError("insufficient historical bars or warmup for year")
        prefix_compiled, prefix_market = _prefix_replay(compiled, market, right)
        forward_start = market.bars[left].timestamp
        evaluated = evaluate_compiled_development(
            prefix_compiled,
            prefix_market,
            initial_cash=initial_cash,
            signal_start_at=forward_start,
        )
        if any(v != initial_cash for v in evaluated.equity_curve[:left]):
            raise ResearchCatalogError("historical data leaked PnL into forward window")
        curve = evaluated.equity_curve[left:]
        if not curve or curve[0] != initial_cash or len(curve) != right - left:
            raise ResearchCatalogError("inherited window first-bar cash boundary mismatch")
        if any(
            datetime.fromisoformat(trade.timestamp) <= forward_start
            for trade in evaluated.trades
        ):
            raise ResearchCatalogError("inherited test window contains pre-close execution")
        forward = MarketDataSet(
            market.version + f"-inherited-year-{year}",
            DataZone.DEVELOPMENT,
            market.bars[left:right],
            market.timeframe,
            market.calendar,
            market.provenance,
        )
        benchmark = compare_qqq_development_benchmarks(
            forward,
            initial_cash=initial_cash,
        )["qqq_costed_buy_and_hold"]
        measured = calculate_metrics(curve, (), periods_per_year=252.0)
        last = forward.bars[-1].timestamp.date()
        periods.append(HistoricalPeriod(
            year=year,
            period_first=forward_start.isoformat(),
            period_last=forward.bars[-1].timestamp.isoformat(),
            year_end_coverage="YEAR_END_OBSERVED" if last.month == 12 else "PARTIAL_YEAR",
            trading_bars=len(forward.bars),
            initial_cash=initial_cash,
            first_holdout_equity=curve[0],
            final_equity=curve[-1],
            total_return=measured.total_return,
            cagr=measured.cagr,
            max_drawdown=measured.max_drawdown,
            sharpe=measured.sharpe,
            completed_trades=sum(t.side == "sell" for t in evaluated.trades),
            fill_count=evaluated.trades_count,
            paid_costs=evaluated.total_paid_costs,
            first_fill=evaluated.trades[0].timestamp if evaluated.trades else None,
            market_qqq_costed_return=benchmark["total_return"],
            excess_costed_return=measured.total_return - benchmark["total_return"],
            evaluation_hash=content_hash({
                "year": year,
                "prefix_replay": evaluated.replay_hash,
                "equity": evaluated.equity_hash,
                "fills": tuple((x.timestamp, x.side, x.price, x.quantity, x.cost)
                               for x in evaluated.trades),
            }),
            benchmark_hash=benchmark["equity_curve_hash"],
        ))
    evidence_hash = str(counted_evidence["audit_hash"])
    return InheritedRobustnessReport(
        strategy_hash=compiled.strategy_hash,
        source_evidence_hash=source_hash,
        full_audit_hash=evidence_hash,
        development_hash=market.dataset_hash,
        cutoff_date=last_development_date.isoformat(),
        periods=tuple(periods),
        report_hash=content_hash({
            "schema": "audited-inherited-ir-historical-v1",
            "full_audit_hash": evidence_hash,
            "source_evidence_hash": source_hash,
            "source_data_hash": market.dataset_hash,
            "years": list(years),
            "periods": [row.__dict__ for row in periods],
            "cutoff": last_development_date.isoformat(),
            "oos_approved": False,
        }),
    )
