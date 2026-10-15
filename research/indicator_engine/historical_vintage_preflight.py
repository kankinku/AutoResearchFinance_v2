"""Read-only historical price vintage readiness and decision-time safety check.

A price snapshot collected *after* a historical decision cannot establish what
was known at that time. A vendor's revision_policy="as_of", a local SHA-256,
and passing an exchange-session cutoff do not independently prove past release
times. This module intentionally has no path to PIT certification or orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from core.data.contracts import DataZone, MarketDataSet

VintagePreflightStatus = Literal[
    "DECISION_TIME_REQUIRED",
    "UNSUPPORTED_DAILY_LABEL",
    "CUTOFF_CONFLICT",
    "UNATTESTED_SNAPSHOT",
    "NO_OBSERVATIONS",
]

_NEW_YORK = ZoneInfo("America/New_York")
_UTC_MIDNIGHT = time(0, 0)
_REGULAR_CLOSE = time(16, 0)


@dataclass(frozen=True)
class HistoricalVintagePreflight:
    status: VintagePreflightStatus
    dataset_hash: str
    source_id: str | None
    revision_policy: str | None
    retrieved_at: str | None
    decision_at: str | None
    bar_count: int
    sessions_past_assumed_close: int | None
    unfinished_or_future_sessions: int | None
    retrieved_after_decision: bool | None
    blocking_reasons: tuple[str, ...]
    point_in_time_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "dataset_hash": self.dataset_hash,
            "source_id": self.source_id,
            "revision_policy": self.revision_policy,
            "retrieved_at": self.retrieved_at,
            "decision_at": self.decision_at,
            "bar_count": self.bar_count,
            "sessions_past_assumed_close": self.sessions_past_assumed_close,
            "unfinished_or_future_sessions": self.unfinished_or_future_sessions,
            "retrieved_after_decision": self.retrieved_after_decision,
            "blocking_reasons": list(self.blocking_reasons),
            "session_close_assumption": (
                "16:00 America/New_York; conservative for early closes; "
                "does not prove vendor release time"
            ),
            "independent_publication_evidence": "MISSING",
            "point_in_time_verified": False,
            "broker_executable": False,
        }


def assess_historical_vintage(
    market: MarketDataSet, *, decision_at: datetime | None = None,
) -> HistoricalVintagePreflight:
    """Check a decision's timestamp boundary; never grant PIT certification.

    US-equity daily bars must use a UTC-midnight *session-date label*.
    Assume the regular 16:00 NY session close as an earliest theoretical
    observation boundary, strictly before decision_at. Real provider release
    can be later. For early closes this conservative rule over-delays use.
    """
    if DataZone(market.zone) is not DataZone.DEVELOPMENT:
        raise ValueError("only development market data may be inspected")
    if market.timeframe != "1d" or market.calendar != "us_equities":
        raise ValueError("vintage preflight requires daily US-equity sessions")
    if decision_at is not None and (
        not isinstance(decision_at, datetime)
        or decision_at.tzinfo is None
        or decision_at.utcoffset() is None
    ):
        raise ValueError("decision_at requires a timezone-aware timestamp")

    source = market.provenance
    at = decision_at.astimezone(timezone.utc) if decision_at is not None else None
    retrieved = source.retrieved_at.astimezone(timezone.utc) if source is not None else None
    reasons = ["independent_publication_attestation_missing"]
    if source is None:
        reasons.append("vendor_provenance_missing")
    elif source.revision_policy == "latest":
        reasons.append("latest_revision_policy_not_historical_as_of")
    if not market.bars:
        reasons.append("market_bars_missing")
    if at is None:
        reasons.append("historical_decision_time_missing")

    retrieved_after = (retrieved > at) if at is not None and retrieved is not None else None
    if retrieved_after:
        reasons.append("captured_after_historical_decision")

    finished: int | None = None
    unfinished: int | None = None
    unsupported = False
    if at is not None and market.bars:
        labels = [bar.timestamp.astimezone(timezone.utc) for bar in market.bars]
        if any(
            label.time() != _UTC_MIDNIGHT or label.microsecond
            for label in labels
        ) or len({label.date() for label in labels}) != len(labels):
            unsupported = True
            reasons.append("non_midnight_utc_daily_session_label")
        else:
            finished = 0
            for label in labels:
                close_ny = datetime.combine(
                    label.date(), _REGULAR_CLOSE, tzinfo=_NEW_YORK
                )
                if close_ny.astimezone(timezone.utc) < at:
                    finished += 1
            unfinished = len(labels) - finished
            if unfinished:
                reasons.append("daily_session_not_closed_at_decision")

    status: VintagePreflightStatus
    if not market.bars:
        status = "NO_OBSERVATIONS"
    elif at is None:
        status = "DECISION_TIME_REQUIRED"
    elif unsupported:
        status = "UNSUPPORTED_DAILY_LABEL"
    elif retrieved_after or unfinished:
        status = "CUTOFF_CONFLICT"
    else:
        status = "UNATTESTED_SNAPSHOT"

    return HistoricalVintagePreflight(
        status=status,
        dataset_hash=market.dataset_hash,
        source_id=source.source_id if source else None,
        revision_policy=source.revision_policy if source else None,
        retrieved_at=retrieved.isoformat() if retrieved else None,
        decision_at=at.isoformat() if at else None,
        bar_count=len(market.bars),
        sessions_past_assumed_close=finished,
        unfinished_or_future_sessions=unfinished,
        retrieved_after_decision=retrieved_after,
        blocking_reasons=tuple(sorted(set(reasons))),
    )
