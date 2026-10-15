"""Issuer distribution spot-check against daily raw/adjusted close factor changes.

The Invesco table is an independent *issuer* cash distribution reference.
Tiingo's historical adjusted close remains latest-revised rather than as-of.
Never promote a checked cash event to full corporate-action/PIT certification.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from typing import Literal

from core.data.contracts import DataZone, MarketDataSet

_REFERENCE = Path(__file__).with_name("issuer_qqq_dividends_v1.json")
_PINNED_SHA256 = "a8c08715ea0fe6b9e80c6e0cea99c12fba8bbed7d2fd54fffccf817a1bfdd6c4"
_TOLERANCE_USD = 0.0001  # issuer amount comparison, not event discovery
_MATERIAL_FACTOR_CHANGE_USD = 0.01  # indicative cash-equivalent change per share
_MAX_DETAIL = 24


@dataclass(frozen=True)
class IssuerDistributionSpotCheck:
    status: Literal[
        "PARTIAL_ISSUER_DISTRIBUTIONS_MATCH",
        "ISSUER_DISTRIBUTION_MISMATCH",
        "NOT_COMPARABLE",
    ]
    issuer: str
    reference_sha256: str
    raw_dataset_hash: str
    adjusted_dataset_hash: str
    checked_events: int
    matched_events: int
    missing_events: tuple[str, ...]
    amount_mismatches: tuple[str, ...]
    implied_cash_events: tuple[tuple[str, float], ...]
    detected_adjustment_events: int
    unreferenced_adjustment_events: int
    unreferenced_adjustment_dates: tuple[str, ...]
    distribution_coverage: Literal["SELECTED_CHECKPOINTS_ONLY"] = "SELECTED_CHECKPOINTS_ONLY"
    all_corporate_actions_verified: Literal[False] = False
    point_in_time_price_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "issuer": self.issuer,
            "reference_sha256": self.reference_sha256,
            "raw_dataset_hash": self.raw_dataset_hash,
            "adjusted_dataset_hash": self.adjusted_dataset_hash,
            "checked_events": self.checked_events,
            "matched_events": self.matched_events,
            "missing_events": list(self.missing_events),
            "amount_mismatches": list(self.amount_mismatches),
            "implied_cash_events": [
                {"ex_date": day, "implied_usd_per_share": amount}
                for day, amount in self.implied_cash_events
            ],
            "detected_adjustment_events": self.detected_adjustment_events,
            "unreferenced_adjustment_events": self.unreferenced_adjustment_events,
            "unreferenced_adjustment_dates": list(self.unreferenced_adjustment_dates),
            "candidate_event_min_cash_equivalent_usd": _MATERIAL_FACTOR_CHANGE_USD,
            "candidate_event_note": (
                "Raw/adjusted close-factor jumps are unclassified candidates, "
                "not independently verified dividends, splits or historical revisions."
            ),
            "distribution_coverage": self.distribution_coverage,
            "all_corporate_actions_verified": False,
            "point_in_time_price_verified": False,
            "broker_executable": False,
        }


def _load_issuer_cash() -> dict[date, float]:
    blob = _REFERENCE.read_bytes()
    if hashlib.sha256(blob).hexdigest() != _PINNED_SHA256:
        raise ValueError("issuer distribution reference integrity mismatch")
    data = json.loads(blob)
    if data.get("schema") != "issuer_qqq_distributions_v1" or data.get("symbol") != "QQQ":
        raise ValueError("issuer distribution reference schema mismatch")
    rows = data.get("rows")
    if not isinstance(rows, list) or len(rows) < 5:
        raise ValueError("insufficient issuer cash distribution checkpoints")
    events: dict[date, float] = {}
    for row in rows:
        when = date.fromisoformat(row["ex_date"])
        amount = row["cash_usd_per_share"]
        if type(amount) not in (float, int) or not isfinite(amount) or amount <= 0:
            raise ValueError("invalid issuer cash distribution amount")
        if when in events:
            raise ValueError("duplicate issuer ex-dividend date")
        events[when] = float(amount)
    return events


def compare_issuer_qqq_cash_to_price_adjustments(
    raw: MarketDataSet, adjusted: MarketDataSet,
) -> IssuerDistributionSpotCheck:
    """Spot-check selected ex-date cash amounts against Tiingo adjustment factors.

    Tiingo's adjustment uses the ex-date close. For no split at the checkpoint,
    cash = close_ex * (factor_ex / factor_previous - 1), where
    factor = adjusted_close / raw_close. This equation MUST NOT be used as proof
    that a split or later revision is historically point-in-time correct.
    """
    source = _load_issuer_cash()
    comparable = (
        raw.zone is DataZone.DEVELOPMENT
        and adjusted.zone is DataZone.DEVELOPMENT
        and raw.timeframe == adjusted.timeframe == "1d"
        and raw.calendar == adjusted.calendar == "us_equities"
        and raw.provenance is not None and adjusted.provenance is not None
        and raw.provenance.source_id == adjusted.provenance.source_id
        and raw.provenance.corporate_action_policy == "raw"
        and adjusted.provenance.corporate_action_policy == "total_return_adjusted"
        and {bar.symbol for bar in raw.bars} == {"QQQ"}
        and {bar.symbol for bar in adjusted.bars} == {"QQQ"}
        and tuple(bar.timestamp for bar in raw.bars) ==
        tuple(bar.timestamp for bar in adjusted.bars)
    )
    def _report(
        status: Literal[
            "PARTIAL_ISSUER_DISTRIBUTIONS_MATCH",
            "ISSUER_DISTRIBUTION_MISMATCH",
            "NOT_COMPARABLE",
        ],
        total: int, matching: int,
        missing: tuple[str, ...] = (), mismatched: tuple[str, ...] = (),
        implied: tuple[tuple[str, float], ...] = (),
        detected: int = 0,
        unreferenced: tuple[str, ...] = (),
    ) -> IssuerDistributionSpotCheck:
        return IssuerDistributionSpotCheck(
            status=status, issuer="Invesco QQQ",
            reference_sha256=_PINNED_SHA256,
            raw_dataset_hash=raw.dataset_hash,
            adjusted_dataset_hash=adjusted.dataset_hash,
            checked_events=total,
            matched_events=matching,
            missing_events=missing[:_MAX_DETAIL],
            amount_mismatches=mismatched[:_MAX_DETAIL],
            implied_cash_events=implied[:_MAX_DETAIL],
            detected_adjustment_events=detected,
            unreferenced_adjustment_events=len(unreferenced),
            unreferenced_adjustment_dates=unreferenced[:_MAX_DETAIL],
        )
    if not comparable or len(raw.bars) < 2:
        return _report("NOT_COMPARABLE", 0, 0)
    raw_by_day = {bar.timestamp.date(): bar for bar in raw.bars}
    adj_by_day = {bar.timestamp.date(): bar for bar in adjusted.bars}
    if len(raw_by_day) != len(raw.bars):
        return _report("NOT_COMPARABLE", 0, 0)
    ordered = tuple(sorted(raw_by_day))
    in_range = {
        when: cash for when, cash in source.items()
        if ordered[0] <= when <= ordered[-1]
    }
    previous_dates = {day: ordered[i - 1] for i, day in enumerate(ordered) if i}
    # Inventory all *material* close-factor changes, rather than only the
    # seven chosen issuer dates. Split events, rounding artefacts and vendor
    # revisions cannot be identified reliably from these two series alone.
    detected = 0
    unreferenced: list[str] = []
    for day, prior_day in previous_dates.items():
        close = raw_by_day[day].close
        factor = adj_by_day[day].close / close
        prior_factor = adj_by_day[prior_day].close / raw_by_day[prior_day].close
        cash_equivalent = close * (factor / prior_factor - 1)
        if abs(cash_equivalent) >= _MATERIAL_FACTOR_CHANGE_USD:
            detected += 1
            if day not in in_range:
                unreferenced.append(day.isoformat())
    if not in_range:
        return _report(
            "NOT_COMPARABLE", 0, 0, detected=detected,
            unreferenced=tuple(unreferenced),
        )
    matched = 0
    missing: list[str] = []
    mismatched: list[str] = []
    computed: list[tuple[str, float]] = []
    for ex_date, issuer_cash in sorted(in_range.items()):
        prior_date = previous_dates.get(ex_date)
        if prior_date is None or ex_date not in raw_by_day:
            missing.append(ex_date.isoformat())
            continue
        close_ex = raw_by_day[ex_date].close
        factor_ex = adj_by_day[ex_date].close / close_ex
        factor_prev = adj_by_day[prior_date].close / raw_by_day[prior_date].close
        implied = close_ex * (factor_ex / factor_prev - 1)
        computed.append((ex_date.isoformat(), implied))
        if abs(implied - issuer_cash) <= _TOLERANCE_USD:
            matched += 1
        else:
            mismatched.append(ex_date.isoformat())
    if missing or mismatched:
        return _report(
            "ISSUER_DISTRIBUTION_MISMATCH", len(in_range), matched,
            tuple(missing), tuple(mismatched), tuple(computed),
            detected=detected, unreferenced=tuple(unreferenced),
        )
    return _report(
        "PARTIAL_ISSUER_DISTRIBUTIONS_MATCH", len(in_range),
        matched, implied=tuple(computed),
        detected=detected, unreferenced=tuple(unreferenced),
    )
