"""Nasdaq QQQ retrospective dividend cash-flow diagnostics (not PIT nor split proof).

Cash distributions are credited on payment dates, NEVER at ex-dates.
The source is a current-revision snapshot and cannot be used as a historical
trade-time signal or claimed as a split-verified total-return series.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Literal

from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError

_COST = CostModel("academic-dividends-retrospective-v1", 1.0, 2.0, SlippageModel(5.0))
_MAX_SOURCE_BYTES = 400_000
_MAX_EVENTS = 200
_SOURCE_URL = "https://api.nasdaq.com/api/quote/QQQ/dividends?assetclass=etf"


@dataclass(frozen=True)
class DividendEvent:
    ex_date: date
    record_date: date
    pay_date: date
    declaration_date: date | None
    usd_per_share: float
    known_at: datetime  # actual download time; not a historical declaration time


@dataclass(frozen=True)
class DividendEvidence:
    events: tuple[DividendEvent, ...]
    start_date: date
    end_date: date
    captured_at: datetime
    source_sha256: str
    snapshot_hash: str
    missing_declaration_dates: int
    status: Literal["LATEST_REVISION_DIVIDENDS_ONLY"] = "LATEST_REVISION_DIVIDENDS_ONLY"
    historically_tradeable: Literal[False] = False
    point_in_time_verified: Literal[False] = False
    split_history_verified: Literal[False] = False
    candidate_promotable: Literal[False] = False

    def is_available_for_decision(self, time: datetime) -> bool:
        if time.tzinfo is None or time.utcoffset() is None:
            raise ResearchCatalogError("decision timestamp must be timezone-aware")
        return self.captured_at <= time


@dataclass(frozen=True)
class RetrospectiveDividendBenchmark:
    dataset_hash: str
    evidence_hash: str
    report_hash: str
    initial_cash: float
    first_open: float
    price_only_final_equity: float
    dividend_cash_final_equity: float
    total_cash_distributions: float
    payout_count: int
    blockers: tuple[str, ...]
    status: Literal["RETROSPECTIVE_DIVIDEND_SCENARIO_ONLY"] = (
        "RETROSPECTIVE_DIVIDEND_SCENARIO_ONLY"
    )
    pit_verified: Literal[False] = False
    total_return_verified: Literal[False] = False
    candidate_promotable: Literal[False] = False
    out_of_sample_approved: Literal[False] = False


def _day(raw: object, *, optional: bool = False) -> date | None:
    if raw in ("N/A", "", None) and optional:
        return None
    if not isinstance(raw, str):
        raise ResearchCatalogError("Nasdaq dividend event date missing")
    try:
        return datetime.strptime(raw, "%m/%d/%Y").date()
    except ValueError as exc:
        raise ResearchCatalogError("Nasdaq dividend event invalid date") from exc


def parse_nasdaq_dividend_snapshot(
    raw: bytes, start: date, end: date, captured_at: datetime,
) -> DividendEvidence:
    if start > end or (end - start).days > 365 * 20:
        raise ResearchCatalogError("invalid dividend date bounds")
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ResearchCatalogError("captured_at needs timezone")
    at = captured_at.astimezone(timezone.utc)
    if not raw or len(raw) > _MAX_SOURCE_BYTES:
        raise ResearchCatalogError("dividend source empty or oversized")
    try:
        body = json.loads(raw)
        if not isinstance(body, dict) or body["status"]["rCode"] != 200:
            raise ValueError("Nasdaq refused request")
        rows = body["data"]["dividends"]["rows"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_EVENTS:
            raise ValueError("Nasdaq dividend payload incomplete")
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise ResearchCatalogError("Nasdaq dividend response invalid") from exc
    events: list[DividendEvent] = []
    keys: set[tuple[date, float]] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ResearchCatalogError("malformed Nasdaq dividend event")
        ex = _day(row.get("exOrEffDate"))
        pay = _day(row.get("paymentDate"))
        rec = _day(row.get("recordDate"))
        declaration = _day(row.get("declarationDate"), optional=True)
        assert ex is not None and pay is not None and rec is not None
        if row.get("type") != "Cash" or row.get("currency") != "USD":
            raise ResearchCatalogError("unsupported dividend event type/currency")
        amount = row.get("amount")
        if not isinstance(amount, str) or not amount.startswith("$"):
            raise ResearchCatalogError("invalid dollar dividend amount")
        try:
            dollars = float(amount.removeprefix("$").replace(",", ""))
        except ValueError as exc:
            raise ResearchCatalogError("non-numeric dividend amount") from exc
        if not isfinite(dollars) or dollars <= 0 or dollars > 100:
            raise ResearchCatalogError("invalid Nasdaq dividend amount")
        if pay < ex or rec < ex or (declaration is not None and declaration > ex):
            raise ResearchCatalogError("impossible dividend event date order")
        if (ex, dollars) in keys:
            raise ResearchCatalogError("duplicate Nasdaq dividend event")
        keys.add((ex, dollars))
        if start <= ex <= end:
            events.append(DividendEvent(ex, rec, pay, declaration, dollars, at))
    events.sort(key=lambda item: (item.ex_date, item.usd_per_share))
    if not events:
        raise ResearchCatalogError("Nasdaq dividend snapshot has no in-range events")
    raw_hash = hashlib.sha256(raw).hexdigest()
    identity = content_hash({
        "version": "nasdaq-latest-dividend-evidence-v1",
        "source": _SOURCE_URL,
        "source_sha256": raw_hash,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "captured_at": at.isoformat(),
        "events": [
            {"ex": event.ex_date.isoformat(), "record": event.record_date.isoformat(),
             "pay": event.pay_date.isoformat(),
             "declaration": event.declaration_date.isoformat()
             if event.declaration_date is not None else None,
             "amount": event.usd_per_share, "known_at": event.known_at.isoformat()}
            for event in events
        ],
        "known_at_only": "capture-not-declaration",
    })
    return DividendEvidence(
        events=tuple(events), start_date=start, end_date=end,
        captured_at=at, source_sha256=raw_hash, snapshot_hash=identity,
        missing_declaration_dates=sum(e.declaration_date is None for e in events),
    )


def retrospective_dividend_benchmark(
    market: MarketDataSet, evidence: DividendEvidence, *, initial_cash: float = 10_000.0,
) -> RetrospectiveDividendBenchmark:
    """Price-only buy and hold + separate cash paid for shares held before ex-date.

    Not a source-adjusted/corporate-action-complete total return, no tax or
    dividend reinvestment, and no unreceived future-payment cash is invented.
    """
    if market.zone is not DataZone.DEVELOPMENT:
        raise ResearchCatalogError("only development dividend benchmark allowed")
    if market.timeframe != "1d" or market.calendar != "us_equities":
        raise ResearchCatalogError("unsupported dividend benchmark timeframe")
    if len(market.bars) < 2 or {bar.symbol for bar in market.bars} != {"QQQ"}:
        raise ResearchCatalogError("requires QQQ single-symbol bars")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ResearchCatalogError("invalid benchmark cash")
    first = market.bars[0]
    last = market.bars[-1]
    first_day, last_day = first.timestamp.date(), last.timestamp.date()
    if evidence.start_date > first_day or evidence.end_date < last_day:
        raise ResearchCatalogError("dividend evidence does not span market window")
    fraction_cost = _COST.calculate(1.0, side="buy", stress_multiplier=1.0).total
    notional = initial_cash / (1 + fraction_cost)
    charge = _COST.calculate(notional, side="buy", stress_multiplier=1.0).total
    cash = initial_cash - notional - charge
    shares = notional / first.open
    paid = tuple(
        event for event in evidence.events
        if first_day < event.ex_date and event.pay_date <= last_day
    )
    distributions = sum(event.usd_per_share * shares for event in paid)
    price_only = cash + shares * last.close
    total_cash_value = price_only + distributions
    blockers = (
        "dividend_latest_revision_not_as_of",
        "historical_declaration_availability_unverified",
        "corporate_split_history_unverified",
        "dividend_reinvestment_and_taxes_excluded",
        "market_data_pit_not_verified",
    )
    report_hash = content_hash({
        "version": "retrospective-dividend-benchmark-v1", "market": market.dataset_hash,
        "events": evidence.snapshot_hash, "initial_cash": initial_cash,
        "cost_model": _COST.version, "purchase_day": first_day.isoformat(),
        "price_only": price_only, "paid": distributions, "payouts": len(paid),
        "blockers": blockers,
    })
    return RetrospectiveDividendBenchmark(
        dataset_hash=market.dataset_hash, evidence_hash=evidence.snapshot_hash,
        report_hash=report_hash, initial_cash=initial_cash, first_open=first.open,
        price_only_final_equity=price_only,
        dividend_cash_final_equity=total_cash_value,
        total_cash_distributions=distributions, payout_count=len(paid),
        blockers=blockers,
    )


def record_nasdaq_dividend_snapshot(
    raw: bytes, start: date, end: date, captured_at: datetime,
    raw_path: Path, manifest_path: Path,
) -> DividendEvidence:
    if raw_path.resolve() == manifest_path.resolve():
        raise ResearchCatalogError("dividend evidence paths must differ")
    if raw_path.exists() or manifest_path.exists():
        raise ResearchCatalogError("dividend evidence output exists; append-only")
    evidence = parse_nasdaq_dividend_snapshot(raw, start, end, captured_at)
    proof = {
        "version": "nasdaq-dividends-v1", "source_url": _SOURCE_URL,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "captured_at": evidence.captured_at.isoformat(),
        "raw_sha256": evidence.source_sha256,
        "snapshot_hash": evidence.snapshot_hash, "events": len(evidence.events),
        "status": evidence.status,
        "pit_verified": False, "total_return_verified": False,
    }
    try:
        for path in (raw_path, manifest_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("xb") as file:
            file.write(raw)
        with manifest_path.open("x", encoding="utf-8") as file:
            json.dump(proof, file, sort_keys=True, indent=2)
            file.write("\n")
    except Exception:
        for path in (raw_path, manifest_path):
            path.unlink(missing_ok=True)
        raise
    return evidence


def verify_dividend_snapshot(raw_path: Path, manifest_path: Path) -> DividendEvidence:
    try:
        if raw_path.stat().st_size > _MAX_SOURCE_BYTES or manifest_path.stat().st_size > 8192:
            raise ValueError("dividend evidence oversized")
        proof = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(proof, dict) or proof.get("version") != "nasdaq-dividends-v1":
            raise ValueError("dividend evidence format invalid")
        if (proof.get("pit_verified") is not False
                or proof.get("total_return_verified") is not False):
            raise ValueError("dividend evidence attempted status escalation")
        if proof.get("source_url") != _SOURCE_URL:
            raise ValueError("dividend source URL mismatch")
        raw = raw_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != proof["raw_sha256"]:
            raise ResearchCatalogError("dividend raw digest mismatch")
        evidence = parse_nasdaq_dividend_snapshot(
            raw, date.fromisoformat(proof["start_date"]),
            date.fromisoformat(proof["end_date"]),
            datetime.fromisoformat(proof["captured_at"]),
        )
        if (evidence.snapshot_hash != proof["snapshot_hash"]
                or len(evidence.events) != proof["events"]):
            raise ResearchCatalogError("dividend manifest snapshot hash mismatch")
        return evidence
    except ResearchCatalogError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ResearchCatalogError("dividend manifest cannot be verified") from exc
