"""Fail-closed cross-source research benchmark reconciliation, NOT vendor PIT proof.

A different source_id is necessary but insufficient evidence of independence.
Never use these diagnostics to promote a candidate, validate OOS, or order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timezone
from math import isfinite
from typing import Literal
from zoneinfo import ZoneInfo

from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import Bar, DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError

_COST = CostModel("academic-cross-source-price-v1", 1.0, 2.0, SlippageModel(5.0))
_NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class CrossSourceBenchmarkAudit:
    primary_hash: str
    reference_hash: str
    reconciliation_hash: str
    primary_provider: str
    reference_provider: str
    symbol: str
    primary_sessions: int
    reference_sessions: int
    overlap_sessions: int
    primary_only_sessions: int
    reference_only_sessions: int
    reference_first_open: float | None
    max_absolute_close_difference: float | None
    max_relative_close_difference: float | None
    field_mismatch_counts: tuple[tuple[str, int], ...]
    field_max_absolute_difference: tuple[tuple[str, float], ...]
    primary_price_only_final_equity: float | None
    reference_price_only_final_equity: float | None
    blockers: tuple[str, ...]
    status: Literal["CROSS_SOURCE_DEVELOPMENT_ONLY", "RECONCILIATION_BLOCKED"]
    point_in_time_verified: Literal[False] = False
    independent_benchmark_verified: Literal[False] = False
    candidate_promotable: Literal[False] = False
    sealed_oos_approved: Literal[False] = False


def _sessions(dataset: MarketDataSet) -> dict[date, Bar]:
    sessions: dict[date, Bar] = {}
    for bar in dataset.bars:
        utc = bar.timestamp.astimezone(timezone.utc)
        # Legacy Tiingo and captured Nasdaq daily bars use UTC midnight as an
        # exchange DATE LABEL, not a midnight price observation. Converting
        # that instant into New York time would shift the session one day.
        key = (
            utc.date() if (utc.hour, utc.minute, utc.second, utc.microsecond)
            == (0, 0, 0, 0) else bar.timestamp.astimezone(_NY).date()
        )
        if key in sessions:
            raise ResearchCatalogError("duplicate exchange session; no intraday aliasing")
        sessions[key] = bar
    return sessions


def _price_only_equity(first: Bar, last: Bar, initial_cash: float) -> float:
    rate = _COST.calculate(1.0, side="buy", stress_multiplier=1.0).total
    notional = initial_cash / (1 + rate)
    commission = _COST.calculate(notional, side="buy", stress_multiplier=1.0).total
    remaining = initial_cash - notional - commission
    result = remaining + (notional / first.open) * last.close
    if not isfinite(result) or result <= 0:
        raise ResearchCatalogError("non-finite cross-source price-only reference")
    return result


def reconcile_development_benchmark(
    primary: MarketDataSet,
    reference: MarketDataSet,
    *,
    initial_cash: float = 10_000.0,
) -> CrossSourceBenchmarkAudit:
    """Compare two separately supplied single-asset datasets without date fill.

    Only identical trading-session coverage and comparable corporate-action
    conventions permit *exploratory* price-only calculations. Unauthenticated
    vendor labels and backfilled revisions cannot certify independent PIT.
    """
    if any(ds.zone != DataZone.DEVELOPMENT for ds in (primary, reference)):
        raise ResearchCatalogError("only development data may be reconciled")
    if any(ds.timeframe != "1d" or ds.calendar != "us_equities"
           for ds in (primary, reference)):
        raise ResearchCatalogError("only daily US equity benchmark supported")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ResearchCatalogError("invalid initial cash for benchmark")
    if any(ds.provenance is None for ds in (primary, reference)):
        raise ResearchCatalogError("both benchmark inputs require source provenance")
    if not primary.bars or not reference.bars:
        raise ResearchCatalogError("benchmark inputs cannot be empty")
    left_symbols = {bar.symbol for bar in primary.bars}
    right_symbols = {bar.symbol for bar in reference.bars}
    if len(left_symbols) != 1 or left_symbols != right_symbols:
        raise ResearchCatalogError("benchmark symbol coverage must match")
    first_source, second_source = primary.provenance, reference.provenance
    assert first_source is not None and second_source is not None
    left, right = _sessions(primary), _sessions(reference)
    left_dates, right_dates = set(left), set(right)
    overlap = sorted(left_dates & right_dates)
    structural: list[str] = []
    if first_source.source_id.strip().casefold() == second_source.source_id.strip().casefold():
        structural.append("same_vendor_identity")
    if len(left_dates ^ right_dates) > 0:
        structural.append("incomplete_session_alignment")
    if first_source.corporate_action_policy != second_source.corporate_action_policy:
        structural.append("incompatible_corporate_action_conventions")
    # Different vendor declarations with bitwise-equivalent historical records
    # may still be the same syndicated underlying feed. Block until audited.
    if len(left_dates) == len(right_dates) and not any(
        (left[d].open, left[d].high, left[d].low, left[d].close, left[d].volume)
        != (right[d].open, right[d].high, right[d].low, right[d].close, right[d].volume)
        for d in overlap
    ):
        structural.append("identical_ohlcv_payload")

    blockers = list(structural)
    if (first_source.revision_policy != "as_of"
            or second_source.revision_policy != "as_of"):
        blockers.append("latest_revision_not_as_of")
    if any(
        source.corporate_action_policy != "total_return_adjusted"
        or not source.corporate_action_reference
        for source in (first_source, second_source)
    ):
        blockers.append("corporate_action_adjustment_unverified")
    # A self-reported as_of flag is neither historical record-availability
    # evidence nor proof that two vendors' values were independently acquired.
    blockers.extend((
        "bar_level_availability_unverified",
        "historical_vintages_not_authenticated",
        "vendor_authenticity_not_verified",
    ))
    blocked = bool(structural)
    left_result: float | None = None
    right_result: float | None = None
    absolute: float | None = None
    relative: float | None = None
    first_open: float | None = None
    if not blocked:
        # Structural condition ensures both date sets are identical and nonempty.
        first_day, last_day = overlap[0], overlap[-1]
        left_result = _price_only_equity(left[first_day], left[last_day], initial_cash)
        right_result = _price_only_equity(right[first_day], right[last_day], initial_cash)
        first_open = right[first_day].open
        absolute = max(abs(left[d].close - right[d].close) for d in overlap)
        relative = max(abs(left[d].close - right[d].close) / left[d].close for d in overlap)
    mismatches: list[tuple[str, int]] = []
    maxima: list[tuple[str, float]] = []
    for field in ("open", "high", "low", "close", "volume"):
        differences = [abs(getattr(left[d], field) - getattr(right[d], field))
                       for d in overlap]
        mismatches.append((field, sum(delta > 1e-8 for delta in differences)))
        maxima.append((field, max(differences, default=0.0)))
    fingerprint = content_hash({
        "version": "cross-source-reconciliation-v1",
        "primary": primary.dataset_hash,
        "reference": reference.dataset_hash,
        "initial_cash": initial_cash,
        "cost": _COST.version,
        "primary_sessions": len(left),
        "reference_sessions": len(right),
        "overlap_sessions": len(overlap),
        "only_primary": len(left_dates - right_dates),
        "only_reference": len(right_dates - left_dates),
        "blockers": blockers,
        "primary_final": left_result,
        "reference_final": right_result,
        "max_abs_close": absolute,
        "max_relative_close": relative,
        "field_mismatch_counts": mismatches,
        "field_max_absolute_difference": maxima,
    })
    return CrossSourceBenchmarkAudit(
        primary_hash=primary.dataset_hash,
        reference_hash=reference.dataset_hash,
        reconciliation_hash=fingerprint,
        primary_provider=first_source.source_id,
        reference_provider=second_source.source_id,
        symbol=next(iter(left_symbols)),
        primary_sessions=len(left),
        reference_sessions=len(right),
        overlap_sessions=len(overlap),
        primary_only_sessions=len(left_dates - right_dates),
        reference_only_sessions=len(right_dates - left_dates),
        reference_first_open=first_open,
        max_absolute_close_difference=absolute,
        max_relative_close_difference=relative,
        field_mismatch_counts=tuple(mismatches),
        field_max_absolute_difference=tuple(maxima),
        primary_price_only_final_equity=left_result,
        reference_price_only_final_equity=right_result,
        blockers=tuple(blockers),
        status="RECONCILIATION_BLOCKED" if blocked else "CROSS_SOURCE_DEVELOPMENT_ONLY",
    )
