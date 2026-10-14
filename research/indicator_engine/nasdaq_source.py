"""Read-only Nasdaq historical QQQ intake for *development*, never PIT/OOS.

Nasdaq publishes a current-revision historical table; a contemporary download
cannot prove what the exchange had made available on a past trade date.
This module uses one fixed HTTPS endpoint (no caller-controlled destination).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from typing import Literal

import httpx

from core.data.contracts import Bar, MarketDataSet, MarketSourceProvenance

_ENDPOINT = "https://api.nasdaq.com/api/quote/QQQ/historical"
_MAX_BODY_BYTES = 3_000_000
_MAX_ROWS = 10_000


class NasdaqSnapshotError(ValueError):
    """Refuse incomplete, malformed, remote-redirected or unbounded snapshots."""


@dataclass(frozen=True)
class NasdaqSnapshot:
    dataset: MarketDataSet
    dataset_hash: str
    response_sha256: str
    source_url: str
    retrieved_at: str
    declared_records: int
    point_in_time_verified: Literal[False] = False
    independent_benchmark_verified: Literal[False] = False
    candidate_promotable: Literal[False] = False


def _price(value: object) -> float:
    if not isinstance(value, str) or not value:
        raise NasdaqSnapshotError("malformed Nasdaq price/volume")
    try:
        parsed = float(value.replace(",", ""))
    except ValueError as exc:
        raise NasdaqSnapshotError("malformed Nasdaq price/volume") from exc
    if not isfinite(parsed):
        raise NasdaqSnapshotError("nonfinite Nasdaq price/volume")
    return parsed


def fetch_nasdaq_qqq(
    start: date,
    end: date,
    *,
    client: httpx.Client | None = None,
    retrieved_at: datetime | None = None,
    max_bars: int = 10_000,
) -> NasdaqSnapshot:
    """Download an exact-range QQQ series; refuse partial or conflicting rows.

    A date-stamped OHLCV bar uses midnight UTC as a *session-date label*,
    matching canonical Tiingo historical input. It is NOT an intraday or
    publication availability timestamp and cannot be used to certify PIT.
    """
    if (
        not isinstance(start, date) or not isinstance(end, date)
        or isinstance(start, datetime) or isinstance(end, datetime)
        or start > end or not 1 <= max_bars <= _MAX_ROWS
        or (end - start).days > 365 * 20
    ):
        raise NasdaqSnapshotError("invalid or unbounded Nasdaq historical request")
    observed = retrieved_at if retrieved_at is not None else datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise NasdaqSnapshotError("retrieval timestamp must include timezone")
    observed = observed.astimezone(timezone.utc)
    if observed.date() < end:
        raise NasdaqSnapshotError("future Nasdaq date cannot be historically retrieved")
    query = {
        "assetclass": "etf",
        "fromdate": start.isoformat(),
        "todate": end.isoformat(),
        "limit": str(max_bars),
    }
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(12.0, connect=4.0),
            follow_redirects=False,
            trust_env=False,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; QuantResearch/0.1; historical-read-only)",
                "Accept": "application/json",
                "Origin": "https://www.nasdaq.com",
                "Referer": "https://www.nasdaq.com/",
            },
        )
    try:
        try:
            resp = client.get(_ENDPOINT, params=query)
        except httpx.HTTPError as exc:
            raise NasdaqSnapshotError("Nasdaq network request failed") from exc
    finally:
        if owns_client:
            client.close()
    if resp.status_code != 200 or resp.history or len(resp.content) > _MAX_BODY_BYTES:
        raise NasdaqSnapshotError("Nasdaq request denied, redirected, or too large")
    try:
        raw = resp.json()
        data = raw["data"]
        if not isinstance(data, dict) or raw["status"]["rCode"] != 200:
            raise ValueError("Nasdaq API rejected request")
        if data["symbol"] != "QQQ":
            raise ValueError("Nasdaq response symbol mismatch")
        total = data["totalRecords"]
        rows = data["tradesTable"]["rows"]
        if (
            type(total) is not int or not isinstance(rows, list)
            or not 1 <= total <= max_bars or len(rows) != total
        ):
            raise ValueError("Nasdaq historical response truncated or empty")
        bars = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("malformed Nasdaq bar")
            session = datetime.strptime(row["date"], "%m/%d/%Y").date()
            if not start <= session <= end:
                raise ValueError("Nasdaq record outside requested date range")
            bars.append(Bar(
                datetime(session.year, session.month, session.day, tzinfo=timezone.utc),
                "QQQ",
                _price(row["open"]), _price(row["high"]),
                _price(row["low"]), _price(row["close"]),
                _price(row["volume"]),
            ))
        # Nasdaq publishes newest first. Reject duplicates and silent reversal.
        timestamps = [bar.timestamp for bar in bars]
        if any(a <= b for a, b in zip(timestamps, timestamps[1:], strict=False)):
            raise ValueError("Nasdaq historical sessions duplicated or unordered")
        bars.reverse()
        dataset = MarketDataSet(
            version=f"nasdaq-public-latest-{observed.date().isoformat()}-{start}-{end}",
            zone="development",
            bars=tuple(bars),
            provenance=MarketSourceProvenance(
                "nasdaq-public", observed, "latest", "single_symbol",
                "raw", None, False,
            ),
        )
    except (KeyError, TypeError, ValueError, AttributeError, json.JSONDecodeError) as exc:
        raise NasdaqSnapshotError("Nasdaq payload failed strict schema validation") from exc
    return NasdaqSnapshot(
        dataset=dataset,
        dataset_hash=dataset.dataset_hash,
        response_sha256=hashlib.sha256(resp.content).hexdigest(),
        source_url=str(resp.request.url),
        retrieved_at=observed.isoformat(),
        declared_records=total,
    )
