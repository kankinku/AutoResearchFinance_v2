"""V03 conservative as-of gate for QQQ cash distributions, splits and revised bars.

Ex-dates, declared *dates*, matched issuer amounts, vendor retrieval times,
and the newest vendor-adjusted OHLCV do not prove historic publication timing.
This module emits evidence only and never changes StrategyIR, fills or orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.corporate_actions import DividendEvidence
from research.indicator_engine.issuer_distribution_reference_v2 import (
    load_qqq_issuer_reference_v2,
    verify_qqq_issuer_distribution_reference_v2,
)
from research.indicator_engine.qqq_split_residual_audit import (
    audit_qqq_split_residuals,
    load_qqq_split_history_secondary_v1,
)


def audit_qqq_corporate_asof(
    raw: MarketDataSet, dividends: DividendEvidence, *,
    decision_at: datetime,
    adjusted: MarketDataSet | None = None,
) -> dict[str, Any]:
    """Report unverified historical release windows without inferring availability.

    A timestamp attached to a *retrieval* is not the timestamp of a historical
    announcement. An ex-date is an entitlement event, not an announcement time;
    adjusted EOD values may incorporate distributions after that decision.
    """
    if (
        not isinstance(decision_at, datetime)
        or decision_at.tzinfo is None
        or decision_at.utcoffset() is None
    ):
        raise ResearchCatalogError("decision_at must have a timezone")
    at = decision_at.astimezone(timezone.utc)
    p = raw.provenance
    if (
        raw.zone is not DataZone.DEVELOPMENT
        or raw.timeframe != "1d" or raw.calendar != "us_equities"
        or len(raw.bars) < 2 or {b.symbol for b in raw.bars} != {"QQQ"}
        or p is None or p.corporate_action_policy != "raw"
        or p.revision_policy != "latest"
        or p.source_id != "tiingo"
        or not dividends.events
        or dividends.status != "LATEST_REVISION_DIVIDENDS_ONLY"
        or dividends.point_in_time_verified is not False
        or dividends.candidate_promotable is not False
    ):
        raise ResearchCatalogError("untrusted QQQ development evidence or source")
    if raw.bars[0].timestamp.date() < dividends.start_date or (
        raw.bars[-1].timestamp.date() > dividends.end_date
    ):
        raise ResearchCatalogError("dividend evidence does not cover price period")
    if any(
        event.known_at != dividends.captured_at or
        event.ex_date < dividends.start_date or
        event.ex_date > dividends.end_date
        for event in dividends.events
    ):
        raise ResearchCatalogError("dividend event and capture chronology mismatch")
    reference = load_qqq_issuer_reference_v2()  # SHA-pinned secondary retained schedule
    split = load_qqq_split_history_secondary_v1()  # secondary, NEVER primary verification
    pair_cash: dict[str, Any] | None = None
    pair_split: dict[str, Any] | None = None
    if adjusted is not None:
        q = adjusted.provenance
        if (
            adjusted.zone is not DataZone.DEVELOPMENT
            or q is None or q.source_id != p.source_id
            or q.corporate_action_policy != "total_return_adjusted"
            or q.revision_policy != "latest"
            or adjusted.timeframe != raw.timeframe
            or adjusted.calendar != raw.calendar
            or tuple(b.timestamp for b in adjusted.bars)
               != tuple(b.timestamp for b in raw.bars)
            or {b.symbol for b in adjusted.bars} != {"QQQ"}
        ):
            raise ResearchCatalogError("incomparable adjusted price input")
        pair_cash = verify_qqq_issuer_distribution_reference_v2(raw, adjusted).record()
        pair_split = audit_qqq_split_residuals(raw, adjusted).record()
    listed = {
        e.ex_date.isoformat(): e for e in dividends.events
    }
    reference_in_window = {
        day: row for day, row in reference.items()
        if dividends.start_date.isoformat() <= day <= dividends.end_date.isoformat()
    }
    matched = sum(
        abs(event.usd_per_share - reference[date]["cash_usd_per_share"]) <= 0.0001
        for date, event in listed.items() if date in reference
    )
    missing = sorted(set(reference_in_window) - set(listed))
    mismatched = sorted(
        day for day in (set(listed) & set(reference))
        if abs(listed[day].usd_per_share - reference[day]["cash_usd_per_share"]) > 0.0001
    )
    prior_events = [e for e in dividends.events if e.ex_date <= at.date()]
    report: dict[str, Any] = {
        "schema": "v03-qqq-corporate-asof-readonly-v1",
        "status": (
            "HISTORICAL_DECISION_PRECEDES_SOURCE_CAPTURE"
            if at < max(dividends.captured_at, p.retrieved_at)
            else "HISTORICAL_PUBLICATION_EVIDENCE_UNATTESTED"
        ),
        "decision_at_utc": at.isoformat(),
        "raw_market_hash": raw.dataset_hash,
        "raw_market_retrieved_at": p.retrieved_at.astimezone(timezone.utc).isoformat(),
        "raw_market_retrieved_by_decision": p.retrieved_at <= at,
        "raw_revision_policy": p.revision_policy,
        "dividend_snapshot_hash": dividends.snapshot_hash,
        "dividend_captured_at": dividends.captured_at.isoformat(),
        "dividend_snapshot_retrieved_by_decision": dividends.captured_at <= at,
        "dividend_source_raw_sha256": dividends.source_sha256,
        "dividend_event_count": len(dividends.events),
        "dividends_ex_date_on_or_before_decision": len(prior_events),
        "dividends_paid_on_or_before_decision": sum(
            e.pay_date <= at.date() for e in prior_events
        ),
        "dividends_ex_prior_but_payment_after_decision": sum(
            e.pay_date > at.date() for e in prior_events
        ),
        "issuer_amounts_matched": matched,
        "issuer_missing_dates": missing[:30],
        "issuer_amount_mismatches": mismatched[:30],
        "dividend_declaration_date_only_count": sum(
            e.declaration_date is not None for e in dividends.events
        ),
        "dividend_declaration_date_missing_count": dividends.missing_declaration_dates,
        "independently_verified_announcement_timestamps": 0,
        "historically_verified_split_events": 0,
        "split_catalog_evidence_class": split["evidence_class"],
        "split_events_in_price_window_secondary": [
            e for e in split["split_events"] if (
                raw.bars[0].timestamp.date().isoformat()
                <= e["date"] <= raw.bars[-1].timestamp.date().isoformat()
            )
        ],
        "latest_adjusted_pair_available": adjusted is not None,
        "adjusted_issuer_cash_check": pair_cash,
        "adjusted_split_residual_check": pair_split,
        "blocking_reasons": [
            "historical_issuer_announcement_timestamp_unattested",
            "dividend_declaration_date_not_publication_timestamp",
            "primary_split_corporate_action_history_unverified",
            "vendor_latest_adjustment_can_embed_future_events",
            "historical_source_price_publication_unattested",
            "asof_vendor_vintage_and_revision_history_unverified",
            *(
                ["price_and_dividend_captured_after_historical_decision"]
                if at < max(dividends.captured_at, p.retrieved_at) else []
            ),
            *(
                ["matching_adjusted_raw_price_pair_missing"]
                if adjusted is None else []
            ),
        ],
        "adjusted_asof_execution_approved": False,
        "asof_dividend_signal_approved": False,
        "historical_point_in_time_verified": False,
        "primary_split_history_verified": False,
        "independent_oos_approved": False,
        "broker_executable": False,
    }
    report["report_hash"] = content_hash(report)
    return report
