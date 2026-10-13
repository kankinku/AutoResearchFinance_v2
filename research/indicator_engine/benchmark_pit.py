"""Independent QQQ comparison and fail-closed PIT metadata audit.

Development diagnostics only: neither a vendor label nor an as-of manifest
establishes historical data authenticity, point-in-time certification, or alpha.
This module has no broker, StrategyIR, sealed-OOS, or promotion integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Literal

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.risk_replay import AcademicRiskReplayResult, _COST


@dataclass(frozen=True)
class BarReleaseEvidence:
    """Claimed historical release and archived-vintage timestamps for one bar."""

    bar_timestamp: datetime
    price_available_at: datetime
    vintage_captured_at: datetime
    vintage_id: str

    def __post_init__(self) -> None:
        for value in (
            self.bar_timestamp,
            self.price_available_at,
            self.vintage_captured_at,
        ):
            if not isinstance(value, datetime) or value.tzinfo is None or (
                value.utcoffset() is None
            ):
                raise ValueError("PIT evidence requires timezone-aware timestamps")
        if not self.vintage_id.strip():
            raise ValueError("archived vintage identifier is required")
        if self.price_available_at < self.bar_timestamp:
            raise ValueError("bar cannot be available before its observation")
        if self.vintage_captured_at < self.price_available_at:
            raise ValueError("vintage cannot precede publication")


@dataclass(frozen=True)
class PitMetadataAudit:
    dataset_hash: str
    evidence_hash: str
    examined_bars: int
    status: Literal["METADATA_CONSISTENT_NOT_CERTIFIED"] = (
        "METADATA_CONSISTENT_NOT_CERTIFIED"
    )
    independently_certified: Literal[False] = False


def audit_pit_metadata(
    dataset: MarketDataSet,
    evidence: tuple[BarReleaseEvidence, ...],
    session_opens: tuple[datetime, ...],
) -> PitMetadataAudit:
    """Check as-of declarations and release-before-next-open causality.

    session_opens[i] is the *actual* market open of the session of bar i,
    provided by a separate exchange calendar. These assertions only check
    consistency of supplied metadata; they cannot attest supplier truth.
    """
    if dataset.zone is not DataZone.DEVELOPMENT or dataset.timeframe != "1d":
        raise ResearchCatalogError("PIT audit accepts development daily bars only")
    provenance = dataset.provenance
    if provenance is None or provenance.revision_policy != "as_of":
        raise ResearchCatalogError("missing historical as-of vendor vintages")
    if (
        provenance.corporate_action_policy != "raw"
        and not provenance.corporate_action_reference
    ):
        raise ResearchCatalogError("adjusted bars require corporate-action lineage")
    if len(dataset.bars) < 2 or len(evidence) != len(dataset.bars):
        raise ResearchCatalogError("PIT evidence must cover every bar")
    if len(session_opens) != len(dataset.bars):
        raise ResearchCatalogError("exchange session opens must cover every bar")
    for i, (bar, record, market_open) in enumerate(
        zip(dataset.bars, evidence, session_opens, strict=True)
    ):
        if market_open.tzinfo is None or market_open.utcoffset() is None:
            raise ResearchCatalogError("market-open timestamp must be timezone-aware")
        if record.bar_timestamp != bar.timestamp:
            raise ResearchCatalogError("PIT evidence bar alignment mismatch")
        if not market_open < bar.timestamp:
            raise ResearchCatalogError("market open must precede completed bar")
        if i:
            previous = evidence[i - 1]
            if previous.price_available_at > market_open:
                raise ResearchCatalogError("signal price was unavailable by next open")
            if previous.vintage_captured_at > market_open:
                raise ResearchCatalogError("archived vintage was not captured by next open")
            if session_opens[i - 1] >= market_open:
                raise ResearchCatalogError("non-increasing market sessions")
    return PitMetadataAudit(
        dataset_hash=dataset.dataset_hash,
        examined_bars=len(dataset.bars),
        evidence_hash=content_hash(
            {
                "dataset": dataset.dataset_hash,
                "records": [
                    {
                        "bar": rec.bar_timestamp.astimezone(timezone.utc).isoformat(),
                        "released": rec.price_available_at.astimezone(timezone.utc).isoformat(),
                        "captured": rec.vintage_captured_at.astimezone(timezone.utc).isoformat(),
                        "vintage": rec.vintage_id,
                        "open": opened.astimezone(timezone.utc).isoformat(),
                    }
                    for rec, opened in zip(evidence, session_opens, strict=True)
                ],
            }
        ),
    )


@dataclass(frozen=True)
class QqqBenchmarkComparison:
    """Price-path comparison, never certified market alpha or OOS evidence."""

    strategy_data_hash: str
    benchmark_data_hash: str
    research_result_hash: str
    comparison_hash: str
    initial_cash: float
    strategy_final_equity: float
    benchmark_final_equity: float
    strategy_total_return: float
    benchmark_total_return: float
    return_spread_percentage_points: float
    benchmark_buy_cost: float
    benchmark_equity_curve: tuple[float, ...]
    strategy_pit_audit_hash: str | None
    benchmark_pit_audit_hash: str | None
    status: Literal["NON_PIT_DEVELOPMENT_COMPARISON"] = "NON_PIT_DEVELOPMENT_COMPARISON"
    independently_verified_benchmark: Literal[False] = False
    verified_alpha: Literal[False] = False
    broker_executable: Literal[False] = False
    candidate_promotable: Literal[False] = False
    out_of_sample_approved: Literal[False] = False


def compare_independent_qqq(
    strategy: AcademicRiskReplayResult,
    strategy_data: MarketDataSet,
    benchmark_data: MarketDataSet,
    *,
    strategy_audit: PitMetadataAudit | None = None,
    benchmark_audit: PitMetadataAudit | None = None,
) -> QqqBenchmarkComparison:
    """Compare marked-to-market strategy vs separately supplied QQQ buy-and-hold.

    QQQ is purchased at the first benchmark open with the SAME model costs
    as risk replay. It is held and valued at each close, without an assumed
    liquidation or sale-cost deduction at the terminal close.
    """
    for data in (strategy_data, benchmark_data):
        if data.zone is not DataZone.DEVELOPMENT:
            raise ResearchCatalogError("benchmark comparison is development-only")
        if data.timeframe != "1d" or data.calendar != "us_equities":
            raise ResearchCatalogError("benchmark requires daily US-equities bars")
        if len(data.bars) < 2 or any(bar.symbol != "QQQ" for bar in data.bars):
            raise ResearchCatalogError("benchmark requires a single QQQ price series")
        if data.provenance is None:
            raise ResearchCatalogError("benchmark comparison requires vendor provenance")
    sp = strategy_data.provenance
    bp = benchmark_data.provenance
    assert sp is not None and bp is not None
    if sp.source_id == bp.source_id or strategy_data.dataset_hash == benchmark_data.dataset_hash:
        raise ResearchCatalogError("benchmark must use an independent source and data object")
    if sp.corporate_action_policy != bp.corporate_action_policy:
        raise ResearchCatalogError("strategy and benchmark adjustment policies differ")
    if (
        sp.corporate_action_policy != "raw"
        and (not sp.corporate_action_reference or not bp.corporate_action_reference)
    ):
        raise ResearchCatalogError("adjusted return comparison needs action lineage")
    if len(strategy_data.bars) != len(benchmark_data.bars) or any(
        s.timestamp != b.timestamp
        for s, b in zip(strategy_data.bars, benchmark_data.bars, strict=True)
    ):
        raise ResearchCatalogError("session timestamps must align exactly")
    if strategy.dataset_hash != strategy_data.dataset_hash:
        raise ResearchCatalogError("strategy replay bound to different price data")
    if len(strategy.equity_curve) != len(strategy_data.bars):
        raise ResearchCatalogError("strategy equity timestamps missing or misaligned")
    if (
        strategy.status != "NON_PIT_DEVELOPMENT_ONLY"
        or strategy.broker_executable
        or strategy.candidate_promotable
        or strategy.benchmark_verified
        or strategy.out_of_sample_approved
    ):
        raise ResearchCatalogError("not a confined development risk replay")
    if strategy.trades_count != len(strategy.trades):
        raise ResearchCatalogError("strategy execution count does not match records")
    if (
        not isfinite(strategy.total_paid_costs)
        or strategy.total_paid_costs < 0
        or abs(strategy.total_paid_costs - sum(t.cost for t in strategy.trades)) > 1e-6
    ):
        raise ResearchCatalogError("strategy transaction cost evidence is inconsistent")
    if content_hash(tuple(strategy.equity_curve)) != strategy.equity_hash:
        raise ResearchCatalogError("strategy equity evidence hash does not match")
    if (
        not isfinite(strategy.initial_cash)
        or strategy.initial_cash <= 0
        or not isfinite(strategy.final_equity)
        or strategy.final_equity <= 0
        or strategy.final_equity != strategy.equity_curve[-1]
        or any(not isfinite(x) or x <= 0 for x in strategy.equity_curve)
    ):
        raise ResearchCatalogError("invalid strategy equity evidence")
    if (strategy_audit is None) != (benchmark_audit is None):
        raise ResearchCatalogError("asymmetric PIT metadata evidence")
    if strategy_audit is not None and benchmark_audit is not None:
        if (
            strategy_audit.dataset_hash != strategy_data.dataset_hash
            or benchmark_audit.dataset_hash != benchmark_data.dataset_hash
        ):
            raise ResearchCatalogError("PIT evidence hashes do not match price paths")
    first_open = benchmark_data.bars[0].open
    initial = strategy.initial_cash
    upfront_rate = _COST.calculate(1.0, side="buy", stress_multiplier=1.0).total
    notional = initial / (1.0 + upfront_rate)
    cost = _COST.calculate(notional, side="buy", stress_multiplier=1.0).total
    units = notional / first_open
    cash = initial - notional - cost
    curve = tuple(cash + units * b.close for b in benchmark_data.bars)
    if any(not isfinite(x) or x <= 0 for x in curve):
        raise ResearchCatalogError("invalid benchmark valuation")
    strategy_return = strategy.final_equity / initial - 1.0
    benchmark_return = curve[-1] / initial - 1.0
    spread = (strategy_return - benchmark_return) * 100.0
    identity = {
        "strategy_data": strategy.dataset_hash,
        "strategy_model": strategy.model_hash,
        "strategy_equity": strategy.equity_hash,
        "benchmark_data": benchmark_data.dataset_hash,
        "model_cost": _COST.version,
        "first_open": first_open,
        "benchmark_equity": curve,
        "strategy_pit": strategy_audit.evidence_hash if strategy_audit else None,
        "benchmark_pit": benchmark_audit.evidence_hash if benchmark_audit else None,
        "adapter_version": 1,
    }
    return QqqBenchmarkComparison(
        strategy_data_hash=strategy_data.dataset_hash,
        benchmark_data_hash=benchmark_data.dataset_hash,
        research_result_hash=strategy.equity_hash,
        comparison_hash=content_hash(identity),
        initial_cash=initial,
        strategy_final_equity=strategy.final_equity,
        benchmark_final_equity=curve[-1],
        strategy_total_return=strategy_return,
        benchmark_total_return=benchmark_return,
        return_spread_percentage_points=spread,
        benchmark_buy_cost=cost,
        benchmark_equity_curve=curve,
        strategy_pit_audit_hash=strategy_audit.evidence_hash if strategy_audit else None,
        benchmark_pit_audit_hash=benchmark_audit.evidence_hash if benchmark_audit else None,
    )
