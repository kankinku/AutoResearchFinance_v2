"""Append-only development capture of public Nasdaq QQQ quote-history bytes.

The separately received quote history is current-revision data, never PIT.
Both the raw server payload and its digest are retained outside Git.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import httpx

from core.data.contracts import MarketDataSet
from core.data.parquet import ParquetDataProvider
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_source import NasdaqSnapshotError, fetch_nasdaq_qqq

_ENDPOINT = "https://api.nasdaq.com/api/quote/QQQ/historical"
_MAX_BYTES = 3_000_000
_MAX_RECORDS = 4000


@dataclass(frozen=True)
class NasdaqCaptureReport:
    dataset_hash: str
    raw_sha256: str
    row_count: int
    captured_at: str
    source_url: str
    output_path: str
    raw_path: str
    manifest_path: str
    status: Literal["NON_PIT_SOURCE_CAPTURE"] = "NON_PIT_SOURCE_CAPTURE"
    point_in_time_verified: Literal[False] = False
    independent_benchmark_verified: Literal[False] = False
    candidate_promotable: Literal[False] = False


def _url(start: date, end: date) -> str:
    if start > end or end - start > timedelta(days=3650):
        raise ResearchCatalogError("invalid or excessive Nasdaq date range")
    return _ENDPOINT + "?" + urlencode({
        "assetclass": "etf", "fromdate": start.isoformat(),
        "todate": end.isoformat(), "limit": str(_MAX_RECORDS),
    })


def _http_fetch(url: str) -> bytes:
    if not url.startswith(_ENDPOINT + "?"):
        raise ResearchCatalogError("unsafe Nasdaq source URL")
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    try:
        with urlopen(Request(url, headers=headers), timeout=12) as response:
            if response.status != 200 or "json" not in response.headers.get("Content-Type", ""):
                raise ResearchCatalogError("Nasdaq response is not HTTP 200 JSON")
            if response.geturl().split("?")[0] != _ENDPOINT:
                raise ResearchCatalogError("Nasdaq HTTP redirect refused")
            body = bytes(response.read(_MAX_BYTES + 1))
    except (OSError, HTTPError, URLError) as exc:
        raise ResearchCatalogError("Nasdaq QQQ fetch failed") from exc
    if not body or len(body) > _MAX_BYTES:
        raise ResearchCatalogError("Nasdaq response empty or oversized")
    return body


def parse_nasdaq_qqq(raw: bytes, start: date, end: date,
                     captured_at: datetime) -> MarketDataSet:
    """Use reviewed Nasdaq parser against exactly the archived raw bytes."""
    _url(start, end)
    if not raw or len(raw) > _MAX_BYTES:
        raise ResearchCatalogError("invalid raw Nasdaq payload size")
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ResearchCatalogError("capture timestamp must be timezone-aware")
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise ValueError("missing Nasdaq payload")
        table = payload["data"].get("tradesTable")
        if not isinstance(table, dict) or table.get("asOf") is not None:
            raise ValueError("unrecognized Nasdaq asOf declaration")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ResearchCatalogError("Nasdaq JSON structure is invalid") from exc

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"Content-Type": "application/json"})

    try:
        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
            snapshot = fetch_nasdaq_qqq(
                start, end, client=client, retrieved_at=captured_at,
                max_bars=_MAX_RECORDS,
            )
    except (NasdaqSnapshotError, ValueError) as exc:
        raise ResearchCatalogError("Nasdaq historical snapshot validation failed") from exc
    if snapshot.response_sha256 != hashlib.sha256(raw).hexdigest():
        raise ResearchCatalogError("Nasdaq response digest mismatch")
    return snapshot.dataset


def capture_nasdaq_qqq(
    start: date, end: date,
    output: Path, raw_path: Path, manifest_path: Path,
    *,
    fetch_bytes: Callable[[str], bytes] = _http_fetch,
    captured_at: datetime | None = None,
) -> NasdaqCaptureReport:
    url = _url(start, end)
    paths = (output, raw_path, manifest_path)
    if len({str(path.resolve()) for path in paths}) != 3:
        raise ResearchCatalogError("capture output paths must differ")
    if any(path.exists() for path in paths):
        raise ResearchCatalogError("capture file already exists; append-only")
    at = captured_at if captured_at is not None else datetime.now(timezone.utc)
    try:
        raw = fetch_bytes(url)
    except OSError as exc:
        raise ResearchCatalogError("Nasdaq QQQ fetch failed") from exc
    market = parse_nasdaq_qqq(raw, start, end, at)
    report = NasdaqCaptureReport(
        dataset_hash=market.dataset_hash,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        row_count=len(market.bars),
        captured_at=at.astimezone(timezone.utc).isoformat(),
        source_url=url,
        output_path=str(output), raw_path=str(raw_path), manifest_path=str(manifest_path),
    )
    try:
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("xb") as file:
            file.write(raw)
        ParquetDataProvider.write(output, market)
        with manifest_path.open("x", encoding="utf-8") as file:
            json.dump(asdict(report), file, indent=2, sort_keys=True)
            file.write("\n")
        if ParquetDataProvider.read(output).dataset_hash != report.dataset_hash:
            raise ResearchCatalogError("Nasdaq parquet round-trip mismatch")
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    return report
