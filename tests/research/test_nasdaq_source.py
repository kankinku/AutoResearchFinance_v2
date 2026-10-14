"""Restricted Nasdaq QQQ development intake; never infer PIT from current snapshot."""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest

from core.data.contracts import DataZone
from research.indicator_engine.nasdaq_source import NasdaqSnapshotError, fetch_nasdaq_qqq


def _response(rows: list[dict[str, str]], *, count: int | None = None,
              symbol: str = "QQQ", status: int = 200):
    return {"data": {"symbol": symbol,
                      "totalRecords": len(rows) if count is None else count,
                      "tradesTable": {"rows": rows}},
            "status": {"rCode": status}}


def _row(day: str, close: str = "101.25"):
    return {"date": day, "close": close, "volume": "123,456",
            "open": "100.00", "high": "102.00", "low": "99.00"}


def _mock(payload, *, status: int = 200, redirect: bool = False):
    def handler(req: httpx.Request):
        assert req.url.host == "api.nasdaq.com"
        assert req.url.path == "/api/quote/QQQ/historical"
        assert req.url.params["assetclass"] == "etf"
        if redirect:
            return httpx.Response(302, headers={"Location": "https://unsafe.example/"})
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_fetches_complete_rows_and_rejects_same_day_execution():
    rows = [_row("01/03/2025", "101.25"), _row("01/02/2025", "100.25")]
    with _mock(_response(rows)) as client:
        result = fetch_nasdaq_qqq(date(2025, 1, 2), date(2025, 1, 3),
                                  client=client, retrieved_at=datetime(2026, 10, 14,
                                                                         tzinfo=timezone.utc))
    assert result.dataset.zone is DataZone.DEVELOPMENT
    assert result.dataset.provenance is not None
    assert result.dataset.provenance.source_id == "nasdaq-public"
    assert result.dataset.provenance.revision_policy == "latest"
    assert result.dataset.provenance.corporate_action_policy == "raw"
    assert len(result.dataset.bars) == 2
    assert result.dataset.bars[0].timestamp == datetime(2025, 1, 2, tzinfo=timezone.utc)
    assert result.dataset.bars[-1].close == 101.25
    assert result.dataset.bars[0].volume == 123456
    assert result.response_sha256 and result.dataset_hash == result.dataset.dataset_hash
    assert result.point_in_time_verified is False
    assert result.candidate_promotable is False
    assert result.source_url.startswith("https://api.nasdaq.com/api/quote/QQQ/historical?")


@pytest.mark.parametrize("payload", [
    _response([_row("01/02/2025")], count=2),
    _response([_row("01/02/2025")], symbol="AAPL"),
    _response([_row("01/02/2025")], status=400),
    _response([_row("01/02/2025"), _row("01/02/2025")]),
    _response([_row("01/02/2026")]),
    _response([_row("01/02/2025", "Infinity")]),
    _response([_row("01/02/2025", "-1.00")]),
    {"data": None, "status": {"rCode": 200}},
])
def test_rejects_bad_response(payload):
    with _mock(payload) as client, pytest.raises(NasdaqSnapshotError):
        fetch_nasdaq_qqq(date(2025, 1, 2), date(2025, 1, 3), client=client)


def test_rejects_remote_redirect_and_http_error():
    with _mock(_response([]), redirect=True) as client, pytest.raises(NasdaqSnapshotError):
        fetch_nasdaq_qqq(date(2025, 1, 2), date(2025, 1, 3), client=client)
    with _mock({}, status=429) as client, pytest.raises(NasdaqSnapshotError):
        fetch_nasdaq_qqq(date(2025, 1, 2), date(2025, 1, 3), client=client)


def test_rejects_bad_dates_and_unbounded_request():
    for start, end, limit in (
        (date(2025, 1, 5), date(2025, 1, 2), 100),
        (date(2020, 1, 2), date(2025, 12, 31), 0),
        (date(2020, 1, 2), date(2025, 12, 31), 100001),
    ):
        with pytest.raises(NasdaqSnapshotError):
            fetch_nasdaq_qqq(start, end, max_bars=limit)
