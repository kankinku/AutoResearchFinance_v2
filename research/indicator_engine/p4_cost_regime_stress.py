"""P4-4: frozen counted-development replay under explicit fee/slippage stress.

No walk-forward *selection*, sealed data, 2026 OOS, or brokerage path.
StrategyIR, causal vectors, fills and equity are replayed through the
existing canonical BacktestEngine. This is a descriptive diagnostic only.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from math import isfinite
from statistics import fmean, pstdev
from typing import Any, Literal

from core.backtest.engine import BacktestEngine, BacktestRequest
from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.decision_audit import (
    AcademicDecisionAudit,
    calculate_audit_hash,
)
from research.indicator_engine.development_benchmark import (
    compare_qqq_development_benchmarks,
)
from research.indicator_engine.strategy_adapter import (
    _COST,
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)


@dataclass(frozen=True)
class StressScenario:
    name: str
    commission_bps: float
    spread_bps: float
    slippage_bps: float
    total_return: float
    max_drawdown: float
    final_equity: float
    closed_trades: int
    fill_count: int
    total_paid_costs: float
    equity_hash: str
    fills_hash: str


@dataclass(frozen=True)
class CalendarPeriod:
    year: int
    daily_bars: int
    strategy_compounded_return: float
    costed_qqq_compounded_return: float
    strategy_minus_qqq_percentage_points: float


@dataclass(frozen=True)
class LaggedRegime:
    label: str
    daily_bars: int
    mean_strategy_daily_return: float
    mean_qqq_daily_return: float
    compounded_strategy_return_on_regime_days: float
    compounded_qqq_return_on_regime_days: float


@dataclass(frozen=True)
class P4DevelopmentStressReport:
    strategy_hash: str
    source_evidence_hash: str
    audit_hash: str
    dataset_hash: str
    baseline_equity_hash: str
    benchmark_curve_hash: str
    cutoff: str
    scenarios: tuple[StressScenario, ...]
    calendar_years: tuple[CalendarPeriod, ...]
    regimes: tuple[LaggedRegime, ...]
    unclassified_warmup_days: int
    report_hash: str
    evaluation_scope: Literal["REUSED_NON_PIT_DEVELOPMENT_DIAGNOSTIC_ONLY"] = (
        "REUSED_NON_PIT_DEVELOPMENT_DIAGNOSTIC_ONLY"
    )
    independent_oos_approved: Literal[False] = False
    candidate_promotable: Literal[False] = False
    broker_executable: Literal[False] = False


def _lagged_regime(market: MarketDataSet, index: int) -> str | None:
    """Signals know closes up to i-1 only. No future-close regime labels."""
    if index < 64 or index >= len(market.bars):
        return None
    closes = [bar.close for bar in market.bars]
    trend = "UP" if closes[index-1] > closes[index-64] else "DOWN"
    last_twenty = [
        closes[j] / closes[j-1] - 1 for j in range(index-20, index)
    ]
    volatility = "HIGH_VOL" if pstdev(last_twenty) > 0.015 else "LOW_VOL"
    return trend + "_" + volatility


def _compound(values: list[float]) -> float:
    result = 1.0
    for value in values:
        result *= 1 + value
    return result - 1


def _scenario(
    name: str, compiled: CompiledAcademicStrategy,
    market: MarketDataSet, cost: CostModel, cash: float,
) -> tuple[StressScenario, tuple[float, ...], tuple[object, ...]]:
    output = BacktestEngine().run(BacktestRequest(
        run_id="p4-ex-post-" + name.lower() + "-" + compiled.strategy_hash[:12],
        strategy_hash=compiled.strategy_hash,
        strategy=compiled.strategy,
        dataset=market,
        cost_model=cost,
        initial_cash=cash,
        feature_values=compiled.feature_values,
    ))
    if (output.exit_status != "SUCCEEDED"
        or output.data_hash != market.dataset_hash
        or len(output.equity_curve) != len(market.bars)
        or content_hash(output.equity_curve) != output.equity_curve_hash):
        raise ResearchCatalogError("P4-4 canonical stress backtest integrity mismatch")
    metrics = calculate_metrics(output.equity_curve, (), periods_per_year=252)
    info = StressScenario(
        name=name,
        commission_bps=cost.commission_bps,
        spread_bps=cost.spread_bps,
        slippage_bps=cost.slippage.basis_points,
        total_return=metrics.total_return,
        max_drawdown=metrics.max_drawdown,
        final_equity=output.equity_curve[-1],
        closed_trades=sum(t.side == "sell" for t in output.trades),
        fill_count=len(output.trades),
        total_paid_costs=sum(t.cost for t in output.trades),
        equity_hash=output.equity_curve_hash,
        fills_hash=content_hash([asdict(t) for t in output.trades]),
    )
    return info, output.equity_curve, output.trades


def evaluate_p4_cost_regime_stress(
    compiled: CompiledAcademicStrategy,
    audit: AcademicDecisionAudit,
    counted_evidence: Mapping[str, Any],
    market: MarketDataSet,
    *,
    last_development_date: date,
) -> P4DevelopmentStressReport:
    """Diagnostic replays require a previously verified audited counted parent.

    Full-period re-evaluation must equal the original signed source equity and
    trade trace. More costly scenarios may re-size trades; they never rewrite
    the underlying counted generation.
    """
    if (market.zone != DataZone.DEVELOPMENT
        or market.timeframe != "1d"
        or market.calendar != "us_equities"
        or len(market.bars) < 100
        or any(b.symbol != "QQQ" for b in market.bars)
        or any(a.timestamp >= b.timestamp for a, b in zip(
            market.bars, market.bars[1:], strict=False,
        ))
        or not isinstance(last_development_date, date)
        or isinstance(last_development_date, datetime)
        or last_development_date > date(2025, 12, 31)
        or market.bars[-1].timestamp.date() > last_development_date):
        raise ResearchCatalogError("P4-4 QQQ cutoff / development policy excludes 2026 or OOS")
    if (compiled.dataset_hash != market.dataset_hash
        or counted_evidence.get("dataset_hash") != market.dataset_hash
        or counted_evidence.get("strategy_hash") != compiled.strategy_hash
        or counted_evidence.get("audit_hash") != audit.trace_hash
        or counted_evidence.get("broker_executable") is not False
        or counted_evidence.get("independent_oos_approved") is not False
        or audit.trace_hash != calculate_audit_hash(
            audit.evaluation, audit.decisions, audit.fills,
            audit.round_trips, audit.llm_packet,
        )
        or audit.evaluation.strategy_hash != compiled.strategy_hash
        or audit.evaluation.dataset_hash != market.dataset_hash
        or type(counted_evidence.get("measured_final_equity")) not in (int, float)
        or not isfinite(counted_evidence["measured_final_equity"])
        or abs(counted_evidence["measured_final_equity"] -
               audit.evaluation.final_equity) > 1e-6
        or not isinstance(counted_evidence.get("metrics"), dict)
        or counted_evidence["metrics"].get("trade_count") != len(audit.round_trips)
        or not isinstance(counted_evidence.get("evidence_hash"), str)
        or len(counted_evidence["evidence_hash"]) != 64):
        raise ResearchCatalogError("P4-4 source strategy / counted evidence mismatch")

    canonical = evaluate_compiled_development(
        compiled, market, initial_cash=audit.evaluation.initial_cash,
    )
    if canonical != audit.evaluation:
        raise ResearchCatalogError("P4-4 original audit canonical replay mismatch")
    scenarios_data = [
        _scenario("CANONICAL", compiled, market, _COST, canonical.initial_cash),
        _scenario("SLIPPAGE_2X", compiled, market, CostModel(
            _COST.version, _COST.commission_bps, _COST.spread_bps,
            SlippageModel(_COST.slippage.basis_points * 2),
        ), canonical.initial_cash),
        _scenario("ALL_TRANSACTION_COSTS_2X", compiled, market, CostModel(
            _COST.version, _COST.commission_bps * 2, _COST.spread_bps * 2,
            SlippageModel(_COST.slippage.basis_points * 2),
        ), canonical.initial_cash),
    ]
    baseline, curve, fills = scenarios_data[0]
    if (curve != canonical.equity_curve or fills != canonical.trades
        or baseline.equity_hash != canonical.equity_hash
        or abs(baseline.total_paid_costs-canonical.total_paid_costs) > 1e-8):
        raise ResearchCatalogError("P4-4 canonical baseline cost/trace parity failed")
    market_benchmark = compare_qqq_development_benchmarks(
        market, initial_cash=canonical.initial_cash, include_equity_curve=True,
    )["qqq_costed_buy_and_hold"]
    qqq = market_benchmark["equity_curve"]
    if (len(qqq) != len(curve)
        or content_hash(qqq) != market_benchmark["equity_curve_hash"]):
        raise ResearchCatalogError("P4-4 QQQ costed curve identity mismatch")
    periods = []
    for year in sorted({b.timestamp.year for b in market.bars}):
        dates = [i for i, b in enumerate(market.bars) if b.timestamp.year == year]
        first, end = dates[0], dates[-1]
        if first == 0:
            start_strategy, start_qqq = curve[0], qqq[0]
        else:
            start_strategy, start_qqq = curve[first-1], qqq[first-1]
        sr, br = curve[end]/start_strategy-1, qqq[end]/start_qqq-1
        periods.append(CalendarPeriod(
            year=year, daily_bars=len(dates), strategy_compounded_return=sr,
            costed_qqq_compounded_return=br,
            strategy_minus_qqq_percentage_points=(sr-br)*100,
        ))
    by_regime: dict[str, tuple[list[float], list[float]]] = {}
    for i in range(1, len(market.bars)):
        regime = _lagged_regime(market, i)
        if regime is None:
            continue
        left, right = by_regime.setdefault(regime, ([], []))
        left.append(curve[i]/curve[i-1]-1)
        right.append(qqq[i]/qqq[i-1]-1)
    regimes = tuple(
        LaggedRegime(
            label=k, daily_bars=len(values[0]),
            mean_strategy_daily_return=fmean(values[0]),
            mean_qqq_daily_return=fmean(values[1]),
            compounded_strategy_return_on_regime_days=_compound(values[0]),
            compounded_qqq_return_on_regime_days=_compound(values[1]),
        ) for k, values in sorted(by_regime.items())
    )
    payload = {
        "schema": "p4-counted-qqq-development-cost-regime-v1",
        "strategy_hash": compiled.strategy_hash,
        "source_evidence_hash": counted_evidence["evidence_hash"],
        "audit_hash": audit.trace_hash,
        "dataset_hash": market.dataset_hash,
        "baseline_equity_hash": baseline.equity_hash,
        "benchmark_curve_hash": market_benchmark["equity_curve_hash"],
        "cutoff": last_development_date.isoformat(),
        "scenarios": [asdict(s[0]) for s in scenarios_data],
        "calendar_years": [asdict(y) for y in periods],
        "regimes": [asdict(r) for r in regimes],
        "regime_selection": "63_DAY_LAGGED_TREND_20_DAY_LAGGED_VOL_THRESHOLD_1P5PCT",
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    return P4DevelopmentStressReport(
        strategy_hash=compiled.strategy_hash,
        source_evidence_hash=counted_evidence["evidence_hash"],
        audit_hash=audit.trace_hash,
        dataset_hash=market.dataset_hash,
        baseline_equity_hash=baseline.equity_hash,
        benchmark_curve_hash=market_benchmark["equity_curve_hash"],
        cutoff=last_development_date.isoformat(),
        scenarios=tuple(data[0] for data in scenarios_data),
        calendar_years=tuple(periods),
        regimes=regimes,
        unclassified_warmup_days=64,
        report_hash=content_hash(payload),
    )
