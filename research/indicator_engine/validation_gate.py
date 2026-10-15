from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite

from core.data.contracts import MarketDataSet
from research.indicator_engine.nyse_public_calendar import (
    verify_published_nyse_regular_sessions,
)


@dataclass(frozen=True)
class ExchangeObservation:
    """Mechanical anomaly scan, NOT an independently maintained NYSE calendar."""

    weekend_bars: tuple[str, ...]
    repeated_session_dates: tuple[str, ...]
    max_adjacent_calendar_gap_days: int
    status: str = "SESSION_CALENDAR_NOT_INDEPENDENTLY_VERIFIED"

    @property
    def has_obvious_anomaly(self) -> bool:
        return bool(self.weekend_bars or self.repeated_session_dates)

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "weekend_bars": list(self.weekend_bars),
            "repeated_session_dates": list(self.repeated_session_dates),
            "max_adjacent_calendar_gap_days": self.max_adjacent_calendar_gap_days,
            "obvious_anomaly": self.has_obvious_anomaly,
            "all_expected_exchange_sessions_verified": False,
            "calendar_independently_verified": False,
        }


def inspect_us_equity_daily_observations(data: MarketDataSet) -> ExchangeObservation:
    """Detect impossible-looking bars without pretending to know NYSE closures.

    The provider's timezone-normalized session *date* must be consistent;
    absence of weekends does not mean all valid weekday sessions are present.
    """
    if data.calendar != "us_equities" or data.timeframe != "1d":
        raise ValueError("US equities 1d required for session anomaly scan")
    weekend: list[str] = []
    duplicate: list[str] = []
    max_gap = 0
    last_by_symbol: dict[str, date] = {}
    for bar in data.bars:
        day = bar.timestamp.date()
        token = f"{bar.symbol}:{day.isoformat()}"
        if day.weekday() >= 5:
            weekend.append(token)
        last = last_by_symbol.get(bar.symbol)
        if last is not None:
            if day == last:
                duplicate.append(token)
            max_gap = max(max_gap, (day - last).days)
        last_by_symbol[bar.symbol] = day
    return ExchangeObservation(
        weekend_bars=tuple(weekend),
        repeated_session_dates=tuple(duplicate),
        max_adjacent_calendar_gap_days=max_gap,
    )


def forward_research_blockers(
    historical: MarketDataSet,
    forward: MarketDataSet,
    *,
    cumulative_return: float,
    sharpe: float | None,
    max_drawdown: float,
    closed_trades: int,
) -> tuple[str, ...]:
    """Fail closed for research success claims even when headline metrics pass.

    A pinned public exchange schedule can confirm dated-session coverage for
    supported years. It cannot prove when OHLCV history was published, so
    historical PIT evidence and sealed OOS approval remain absent.
    """
    checks = (
        ("nonpositive_forward_return", cumulative_return <= 0),
        ("forward_sharpe_below_threshold", sharpe is None or not isfinite(sharpe) or sharpe <= .5),
        ("forward_drawdown_above_threshold", max_drawdown > .20),
        ("insufficient_closed_trades", closed_trades < 10),
        ("short_forward_evaluation_window", len(forward.bars) < 252),
    )
    reasons = [key for key, trigger in checks if trigger]
    for role, data in (("historical", historical), ("forward", forward)):
        session = inspect_us_equity_daily_observations(data)
        if session.weekend_bars:
            reasons.append(f"{role}_weekend_session_bar")
        if session.repeated_session_dates:
            reasons.append(f"{role}_repeated_session_date")
        if session.max_adjacent_calendar_gap_days > 8:
            reasons.append(f"{role}_unusually_long_session_gap")
        public = verify_published_nyse_regular_sessions(data)
        if not public.regular_session_schedule_matched:
            reasons.append(f"{role}_official_nyse_session_mismatch_or_unavailable")
        p = data.provenance
        if p is None:
            reasons.append(f"{role}_market_provenance_missing")
        else:
            if p.revision_policy != "as_of":
                reasons.append(f"{role}_revisions_not_as_of")
            if p.corporate_action_policy == "raw" or not p.corporate_action_reference:
                reasons.append(f"{role}_corporate_actions_unverified")
    reasons += [
        "independent_historical_publication_proof_missing",
        "sealed_out_of_sample_approval_missing",
    ]
    return tuple(sorted(set(reasons)))
