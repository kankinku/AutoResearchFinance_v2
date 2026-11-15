"""Keyless Nasdaq EOD is a development snapshot, not independent PIT market truth."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from application.market_data_service import (
    MarketDataError,
    MarketDataService,
    NasdaqDailyProvider,
)
from integrations.chatgpt_mcp_sdk import chatgpt_tools


def _sample(
    *,
    total: int = 2,
    rows: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    if rows is None:
        rows = [
            {
                "date": "01/03/2024",
                "open": "$101.25",
                "high": "102.10",
                "low": "100.00",
                "close": "$101.75",
                "volume": "2,100,000",
            },
            {
                "date": "01/02/2024",
                "open": "100",
                "high": "101.0",
                "low": "99.0",
                "close": "100.50",
                "volume": "1,900,000",
            },
        ]
    return {"data": {"symbol": "QQQ", "totalRecords": total, "tradesTable": {"rows": rows}}}


def test_nasdaq_fixed_host_keyless_quote_parses_and_sorts() -> None:
    captured: list[httpx.Request] = []

    def mock(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_sample())

    provider = NasdaqDailyProvider(transport=httpx.MockTransport(mock))
    bars = provider.daily_bars("QQQ", date(2024, 1, 2), date(2024, 1, 3), adjusted=False)
    assert len(bars) == 2
    assert [bar.timestamp.date().isoformat() for bar in bars] == [
        "2024-01-02", "2024-01-03"
    ]
    assert bars[0].close == 100.50
    assert bars[1].volume == 2_100_000
    assert captured[0].url.host == "api.nasdaq.com"
    assert captured[0].url.path == "/api/quote/QQQ/historical"
    assert captured[0].url.params["fromdate"] == "2024-01-02"
    assert captured[0].url.params["todate"] == "2024-01-03"
    assert "authorization" not in captured[0].headers


@pytest.mark.parametrize(
    ("status", "response", "code"),
    [
        (429, None, "PROVIDER_RATE_LIMITED"),
        (403, None, "PROVIDER_UNAVAILABLE"),
        (200, _sample(total=3), "INCOMPLETE_RANGE"),
        (200, _sample(rows=[{"date": "01/02/2024"}], total=1), "INVALID_VENDOR_DATA"),
        (200, _sample(rows=[{
            "date": "01/02/2024", "open": "100", "high": "102",
            "low": "90", "close": "NaN", "volume": "100",
        }], total=1), "INVALID_VENDOR_DATA"),
        (
            200,
            {"data": {"symbol": "SPY", "totalRecords": 0, "tradesTable": {"rows": []}}},
            "INVALID_VENDOR_DATA",
        ),
    ],
)
def test_nasdaq_malformed_or_refused_data_never_silently_passes(
    status: int, response: dict[str, object] | None, code: str,
) -> None:
    provider = NasdaqDailyProvider(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=response or {})
        )
    )
    with pytest.raises(MarketDataError) as error:
        provider.daily_bars("QQQ", date(2024, 1, 2), date(2024, 1, 3), adjusted=False)
    assert error.value.code == code
    assert "request" not in str(error.value).lower()


def test_nasdaq_provider_is_listed_and_download_is_immutable(tmp_path: Path) -> None:
    calls = 0

    def mock(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_sample())

    provider = NasdaqDailyProvider(transport=httpx.MockTransport(mock))
    market = MarketDataService(tmp_path, providers={"nasdaq": provider})
    result = market.download(
        provider="nasdaq",
        symbol="QQQ",
        start="2024-01-02",
        end="2024-01-03",
        price_policy="raw",
    )
    assert result["status"] == "DOWNLOADED"
    assert result["bars"] == 2
    assert result["source_id"] == "nasdaq"
    assert result["quality"]["point_in_time_verified"] is False
    assert result["point_in_time_independently_verified"] is False
    assert result["orders_enabled"] is False
    assert result["data_path"] == "data/market/nasdaq/QQQ_2024-01-02_2024-01-03_raw.parquet"
    again = market.download(
        provider="nasdaq", symbol="QQQ", start="2024-01-02", end="2024-01-03",
    )
    assert again["status"] == "ALREADY_EXISTS"
    assert again["dataset_hash"] == result["dataset_hash"]
    assert calls == 1
    assert market.list_datasets()["count"] == 1
    assert {"nasdaq", "tiingo", "kis"} <= {
        item["name"] for item in market.provider_status()["providers"]
    }
    tool = next(t for t in chatgpt_tools() if t["name"] == "download_market_data")
    # ABI is frozen: the new source is loaded from a verified managed Parquet,
    # not exposed as an unapproved additional MCP download enum member.
    assert tool["inputSchema"]["properties"]["provider"]["enum"] == ["tiingo", "kis"]
    with pytest.raises(MarketDataError) as error:
        market.download(
            provider="nasdaq", symbol="QQQ",
            start="2024-01-02", end="2024-01-03",
            price_policy="total_return_adjusted",
        )
    assert error.value.code == "POLICY_UNSUPPORTED"
