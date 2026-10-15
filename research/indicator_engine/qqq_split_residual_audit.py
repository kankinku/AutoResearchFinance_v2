"""QQQ cash-adjustment residual and secondary-only split catalog audit.

Latest-revised EOD raw/adjusted observations and independently sourced issuer
cash may reveal unexplained split-like factor jumps. No absence-of-split or
historical point-in-time proof is possible without primary signed vintages.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Literal, TypedDict, cast

from core.data.contracts import DataZone, MarketDataSet
from research.indicator_engine.issuer_distribution_reference_v2 import (
    load_qqq_issuer_reference_v2,
)

_REFERENCE = Path(__file__).with_name("qqq_split_history_secondary_v1.json")
_PINNED_SHA256 = "7282cc697081ce1861688acd3c1fad373db79c4bf44d37e341b525a6f6473a45"
_CASH_MATCH_TOLERANCE = 0.0001
_SPLIT_LIKE_CASH_RESIDUAL_USD = 0.01
_MAX_DETAILS = 24
_START = date(2020, 1, 2)
_END = date(2025, 12, 31)

SplitAuditStatus = Literal[
    "NO_UNEXPLAINED_FACTOR_EVENTS",
    "UNEXPLAINED_FACTOR_EVENTS",
    "CASH_AMOUNT_MISMATCH",
    "INCOMPLETE_ISSUER_CASH_OBSERVATIONS",
    "NOT_COMPARABLE",
]


class SplitRecord(TypedDict):
    date: str
    numerator: int
    denominator: int


class SecondarySplitCatalog(TypedDict):
    split_events: list[SplitRecord]
    sources: list[dict[str, str]]
    evidence_class: Literal["SECONDARY_AGGREGATOR_ONLY"]


@dataclass(frozen=True)
class QqqSplitResidualReport:
    status: SplitAuditStatus
    reference_sha256: str
    raw_dataset_hash: str
    adjusted_dataset_hash: str
    cash_events_matched: int
    missing_cash_event_dates: tuple[str, ...]
    cash_mismatch_dates: tuple[str, ...]
    potential_split_or_revision_events: int
    potential_event_dates: tuple[str, ...]
    maximum_cash_equivalent_residual_usd: float
    known_split_events_in_window: int
    secondary_split_catalog_sources: int
    full_reference_window_covered: bool
    primary_split_history_verified: Literal[False] = False
    point_in_time_price_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reference_sha256": self.reference_sha256,
            "raw_dataset_hash": self.raw_dataset_hash,
            "adjusted_dataset_hash": self.adjusted_dataset_hash,
            "cash_events_matched": self.cash_events_matched,
            "missing_cash_event_dates": list(self.missing_cash_event_dates),
            "cash_mismatch_dates": list(self.cash_mismatch_dates),
            "potential_split_or_revision_events": self.potential_split_or_revision_events,
            "potential_event_dates": list(self.potential_event_dates),
            "maximum_cash_equivalent_residual_usd": self.maximum_cash_equivalent_residual_usd,
            "known_split_events_in_window": self.known_split_events_in_window,
            "secondary_split_catalog_sources": self.secondary_split_catalog_sources,
            "full_reference_window_covered": self.full_reference_window_covered,
            "evidence_class": "SECONDARY_SPLIT_CATALOG_PLUS_ISSUER_CASH",
            "note": "No unexplained factor jumps does not prove no stock splits or historical PIT.",
            "primary_split_history_verified": False,
            "point_in_time_price_verified": False,
            "broker_executable": False,
        }


def load_qqq_split_history_secondary_v1() -> SecondarySplitCatalog:
    blob = _REFERENCE.read_bytes()
    if hashlib.sha256(blob).hexdigest() != _PINNED_SHA256:
        raise ValueError("split reference integrity mismatch")
    data: object = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("split reference invalid structure")
    d = cast(dict[str, object], data)
    if (
        d.get("schema") != "qqq_split_history_secondary_v1"
        or d.get("symbol") != "QQQ"
        or d.get("evidence_class") != "SECONDARY_AGGREGATOR_ONLY"
        or d.get("window_start") != _START.isoformat()
        or d.get("window_end") != _END.isoformat()
        or d.get("primary_exchange_or_issuer_history_verified") is not False
    ):
        raise ValueError("invalid split reference scope or provenance")
    raw_sources = d.get("sources")
    raw_splits = d.get("split_events")
    if (
        not isinstance(raw_sources, list)
        or len(raw_sources) < 2
        or not isinstance(raw_splits, list)
    ):
        raise ValueError("incomplete secondary split source inventory")
    sources = cast(list[dict[str, str]], raw_sources)
    splits = cast(list[SplitRecord], raw_splits)
    if (
        any(
            not item.get("id") or not item.get("url", "").startswith("https://")
            for item in sources
        )
        or splits != [{"date": "2000-03-20", "numerator": 2, "denominator": 1}]
    ):
        raise ValueError("invalid secondary split evidence")
    return {
        "split_events": splits,
        "sources": sources,
        "evidence_class": "SECONDARY_AGGREGATOR_ONLY",
    }


def audit_qqq_split_residuals(
    raw: MarketDataSet,
    adjusted: MarketDataSet,
) -> QqqSplitResidualReport:
    """Subtract independently referenced cash from daily factor movements.

    Residuals may reflect splits, vendor revisions, special events or faulty
    adjustments; the scan never classifies them as a proven corporate action.
    """
    catalog = load_qqq_split_history_secondary_v1()
    cash_reference = load_qqq_issuer_reference_v2()
    p, q = raw.provenance, adjusted.provenance
    comparable = (
        raw.zone is DataZone.DEVELOPMENT
        and adjusted.zone is DataZone.DEVELOPMENT
        and raw.timeframe == adjusted.timeframe == "1d"
        and raw.calendar == adjusted.calendar == "us_equities"
        and p is not None and q is not None
        and p.source_id == q.source_id
        and p.corporate_action_policy == "raw"
        and q.corporate_action_policy == "total_return_adjusted"
        and {b.symbol for b in raw.bars} == {"QQQ"}
        and {b.symbol for b in adjusted.bars} == {"QQQ"}
        and tuple(b.timestamp for b in raw.bars) == tuple(b.timestamp for b in adjusted.bars)
    )
    def report(
        status: SplitAuditStatus,
        *, matched: int = 0, missing: tuple[str, ...] = (),
        mismatched: tuple[str, ...] = (), residuals: tuple[str, ...] = (),
        max_residual: float = 0.0, full: bool = False,
        splits_in_window: int = 0,
    ) -> QqqSplitResidualReport:
        return QqqSplitResidualReport(
            status=status, reference_sha256=_PINNED_SHA256,
            raw_dataset_hash=raw.dataset_hash,
            adjusted_dataset_hash=adjusted.dataset_hash,
            cash_events_matched=matched,
            missing_cash_event_dates=missing[:_MAX_DETAILS],
            cash_mismatch_dates=mismatched[:_MAX_DETAILS],
            potential_split_or_revision_events=len(residuals),
            potential_event_dates=residuals[:_MAX_DETAILS],
            maximum_cash_equivalent_residual_usd=max_residual,
            known_split_events_in_window=splits_in_window,
            secondary_split_catalog_sources=len(catalog["sources"]),
            full_reference_window_covered=full,
        )
    if not comparable or len(raw.bars) < 2:
        return report("NOT_COMPARABLE")
    raw_by_date = {bar.timestamp.date(): bar for bar in raw.bars}
    adj_by_date = {bar.timestamp.date(): bar for bar in adjusted.bars}
    if len(raw_by_date) != len(raw.bars) or len(adj_by_date) != len(adjusted.bars):
        return report("NOT_COMPARABLE")
    ordered = sorted(raw_by_date)
    full = ordered[0] <= _START and ordered[-1] >= _END
    reference = {
        date.fromisoformat(k): v for k, v in cash_reference.items()
        if ordered[0] <= date.fromisoformat(k) <= ordered[-1]
    }
    missing = tuple(sorted(
        day.isoformat() for day in reference if day not in raw_by_date or day == ordered[0]
    ))
    splits_in_window = sum(
        ordered[0] <= date.fromisoformat(item["date"]) <= ordered[-1]
        for item in catalog["split_events"]
    )
    mismatched: list[str] = []
    residuals: list[str] = []
    matched = 0
    max_residual = 0.0
    for previous, current in zip(ordered, ordered[1:], strict=False):
        raw_close = raw_by_date[current].close
        adj_factor = adj_by_date[current].close / raw_close
        prev_factor = adj_by_date[previous].close / raw_by_date[previous].close
        implied_cash_equivalent = raw_close * (adj_factor / prev_factor - 1)
        expected_cash = reference[current]["cash_usd_per_share"] if current in reference else 0.0
        residual = abs(implied_cash_equivalent - expected_cash)
        if not isfinite(residual):
            raise ValueError("non-finite adjustment residual")
        max_residual = max(max_residual, residual)
        if current in reference:
            if residual <= _CASH_MATCH_TOLERANCE:
                matched += 1
            else:
                mismatched.append(current.isoformat())
        elif residual >= _SPLIT_LIKE_CASH_RESIDUAL_USD:
            residuals.append(current.isoformat())
    status: SplitAuditStatus
    if missing:
        status = "INCOMPLETE_ISSUER_CASH_OBSERVATIONS"
    elif mismatched:
        status = "CASH_AMOUNT_MISMATCH"
    elif residuals:
        status = "UNEXPLAINED_FACTOR_EVENTS"
    else:
        status = "NO_UNEXPLAINED_FACTOR_EVENTS"
    return report(
        status, matched=matched, missing=missing,
        mismatched=tuple(mismatched), residuals=tuple(residuals),
        max_residual=max_residual, full=full, splits_in_window=splits_in_window,
    )
