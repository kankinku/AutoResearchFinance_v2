"""Pinned full QQQ cash event schedule vs latest-revised adjusted-price factors.

Issuer date/amount reconciliation only. Neither split inventory nor historical
as-of executable prices, survivorship, or independent point-in-time is proven.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Literal, TypedDict

from core.data.contracts import DataZone, MarketDataSet

ReferenceStatus = Literal[
    "MATCHED_REFERENCE_CASH_EVENTS", "UNREFERENCED_ADJUSTMENT_EVENTS",
    "ISSUER_CASH_AMOUNT_MISMATCH", "ISSUER_REFERENCE_DATE_MISSING",
    "NOT_COMPARABLE",
]

_REFERENCE = Path(__file__).with_name("issuer_qqq_distributions_v2.json")
_PINNED_SHA256 = "c3afbcf1ec20a14202a3ec2656c0b55dc5fc185320d7527210b3887074d2ca83"
_CASH_TOLERANCE = 0.0001
_CANDIDATE_THRESHOLD = 0.01
_FULL_START = date(2020, 1, 2)
_FULL_END = date(2025, 12, 31)
_MAX_EXAMPLES = 24


class IssuerCashRow(TypedDict):
    cash_usd_per_share: float
    kind: Literal["REGULAR_CASH", "SPECIAL_CASH"]
    source_id: str


@dataclass(frozen=True)
class IssuerCashReferenceReport:
    status: ReferenceStatus
    reference_sha256: str
    raw_dataset_hash: str
    adjusted_dataset_hash: str
    reference_events_in_window: int
    matched_events: int
    matched_special_cash_events: int
    mismatched_reference_dates: tuple[str, ...]
    missing_reference_dates: tuple[str, ...]
    unreferenced_candidate_events: int
    unreferenced_candidate_dates: tuple[str, ...]
    full_reference_window_covered: bool
    distribution_cash_schedule_reconciled: bool
    all_corporate_actions_verified: Literal[False] = False
    point_in_time_price_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reference_sha256": self.reference_sha256,
            "raw_dataset_hash": self.raw_dataset_hash,
            "adjusted_dataset_hash": self.adjusted_dataset_hash,
            "reference_events_in_window": self.reference_events_in_window,
            "matched_events": self.matched_events,
            "matched_special_cash_events": self.matched_special_cash_events,
            "mismatched_reference_dates": list(self.mismatched_reference_dates),
            "missing_reference_dates": list(self.missing_reference_dates),
            "unreferenced_candidate_events": self.unreferenced_candidate_events,
            "unreferenced_candidate_dates": list(self.unreferenced_candidate_dates),
            "full_reference_window_covered": self.full_reference_window_covered,
            "distribution_cash_schedule_reconciled": self.distribution_cash_schedule_reconciled,
            "coverage_scope": "QQQ 2020-01-02 to 2025-12-31 cash events only",
            "all_corporate_actions_verified": False,
            "point_in_time_price_verified": False,
            "broker_executable": False,
        }


def load_qqq_issuer_reference_v2() -> dict[str, IssuerCashRow]:
    data_bytes = _REFERENCE.read_bytes()
    if hashlib.sha256(data_bytes).hexdigest() != _PINNED_SHA256:
        raise ValueError("issuer v2 reference integrity mismatch")
    document = json.loads(data_bytes)
    if (
        document.get("schema") != "issuer_qqq_distributions_v2"
        or document.get("symbol") != "QQQ"
        or document.get("scope_start") != _FULL_START.isoformat()
        or document.get("scope_end") != _FULL_END.isoformat()
    ):
        raise ValueError("issuer v2 schema or scope mismatch")
    sources = {x["id"] for x in document["sources"]}
    records: dict[str, IssuerCashRow] = {}
    for item in document["rows"]:
        day = date.fromisoformat(item["ex_date"]).isoformat()
        amount = item["cash_usd_per_share"]
        if (
            day in records
            or not (_FULL_START <= date.fromisoformat(day) <= _FULL_END)
            or type(amount) not in (int, float)
            or not isfinite(amount)
            or amount <= 0
            or item["kind"] not in ("REGULAR_CASH", "SPECIAL_CASH")
            or item["source_id"] not in sources
        ):
            raise ValueError("invalid or duplicate issuer v2 cash reference")
        records[day] = {
            "cash_usd_per_share": float(amount),
            "kind": item["kind"],
            "source_id": item["source_id"],
        }
    if len(records) != 25:
        raise ValueError("incomplete issuer v2 cash reference")
    return records


def verify_qqq_issuer_distribution_reference_v2(
    raw: MarketDataSet, adjusted: MarketDataSet,
) -> IssuerCashReferenceReport:
    source = load_qqq_issuer_reference_v2()
    comparable = (
        raw.zone is DataZone.DEVELOPMENT
        and adjusted.zone is DataZone.DEVELOPMENT
        and raw.timeframe == adjusted.timeframe == "1d"
        and raw.calendar == adjusted.calendar == "us_equities"
        and raw.provenance is not None
        and adjusted.provenance is not None
        and raw.provenance.source_id == adjusted.provenance.source_id
        and raw.provenance.corporate_action_policy == "raw"
        and adjusted.provenance.corporate_action_policy == "total_return_adjusted"
        and {bar.symbol for bar in raw.bars} == {"QQQ"}
        and {bar.symbol for bar in adjusted.bars} == {"QQQ"}
        and tuple(bar.timestamp for bar in raw.bars)
        == tuple(bar.timestamp for bar in adjusted.bars)
    )
    def report(
        status: ReferenceStatus,
        *, relevant: int = 0, matched: int = 0, specials: int = 0,
        missing: tuple[str, ...] = (), mismatched: tuple[str, ...] = (),
        unknown: tuple[str, ...] = (), full: bool = False,
    ) -> IssuerCashReferenceReport:
        return IssuerCashReferenceReport(
            status=status, reference_sha256=_PINNED_SHA256,
            raw_dataset_hash=raw.dataset_hash,
            adjusted_dataset_hash=adjusted.dataset_hash,
            reference_events_in_window=relevant, matched_events=matched,
            matched_special_cash_events=specials,
            missing_reference_dates=missing[:_MAX_EXAMPLES],
            mismatched_reference_dates=mismatched[:_MAX_EXAMPLES],
            unreferenced_candidate_events=len(unknown),
            unreferenced_candidate_dates=unknown[:_MAX_EXAMPLES],
            full_reference_window_covered=full,
            distribution_cash_schedule_reconciled=(
                status == "MATCHED_REFERENCE_CASH_EVENTS" and full
            ),
        )
    if not comparable or len(raw.bars) < 2:
        return report("NOT_COMPARABLE")
    r = {x.timestamp.date().isoformat(): x for x in raw.bars}
    a = {x.timestamp.date().isoformat(): x for x in adjusted.bars}
    if len(r) != len(raw.bars) or len(a) != len(adjusted.bars):
        return report("NOT_COMPARABLE")
    ordered = sorted(r)
    relevant = {
        d: info for d, info in source.items()
        if ordered[0] <= d <= ordered[-1]
    }
    if not relevant:
        return report("NOT_COMPARABLE")
    full = (
        ordered[0] <= _FULL_START.isoformat()
        and ordered[-1] >= _FULL_END.isoformat()
    )
    missing = tuple(sorted(d for d in relevant if d not in r or d == ordered[0]))
    mismatched = []
    unknown = []
    matched = 0
    specials = 0
    for prior_day, day in zip(ordered, ordered[1:], strict=False):
        base = r[day].close
        implied = base * (
            (a[day].close / base)
            / (a[prior_day].close / r[prior_day].close) - 1
        )
        if day in relevant:
            expected = relevant[day]["cash_usd_per_share"]
            if abs(implied - expected) <= _CASH_TOLERANCE:
                matched += 1
                if relevant[day]["kind"] == "SPECIAL_CASH":
                    specials += 1
            else:
                mismatched.append(day)
        elif abs(implied) >= _CANDIDATE_THRESHOLD:
            unknown.append(day)
    status: ReferenceStatus
    if missing:
        status = "ISSUER_REFERENCE_DATE_MISSING"
    elif mismatched:
        status = "ISSUER_CASH_AMOUNT_MISMATCH"
    elif unknown:
        status = "UNREFERENCED_ADJUSTMENT_EVENTS"
    else:
        status = "MATCHED_REFERENCE_CASH_EVENTS"
    return report(
        status, relevant=len(relevant), matched=matched, specials=specials,
        missing=missing, mismatched=tuple(mismatched), unknown=tuple(unknown), full=full,
    )
