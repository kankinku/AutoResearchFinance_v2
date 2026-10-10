"""Market data ingestion: sanitized provider responses, immutable files and MCP routing."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from mcp.types import CallToolRequestParams

from application.market_data_service import (
    MarketDataError,
    MarketDataService,
    TiingoDailyProvider,
)
from core.data.contracts import Bar, DataZone
from core.data.parquet import ParquetDataProvider
from integrations.chatgpt_mcp_sdk import chatgpt_tools, create_chatgpt_sdk_adapter
from integrations.kis.client import KISPaperClient, KISResponse
from integrations.kis.config import PaperKISConfig
from tests.integrations.test_kis_client import RecordingTransport, _env


def _rows(symbol: str, first: date, last: date) -> tuple[Bar, ...]:
    return tuple(
        Bar(
            datetime.combine(first + timedelta(days=i), datetime.min.time(), timezone.utc),
            symbol,
            100.0 + i,
            103.0 + i,
            99.0 + i,
            101.0 + i,
            1000.0 + i,
        )
        for i in range((last - first).days + 1)
    )


class FakePriceProvider:
    def __init__(self) -> None:
        self.calls = 0

    def daily_bars(self, symbol: str, start: date, end: date, *, adjusted: bool) -> tuple[Bar, ...]:
        self.calls += 1
        return _rows(symbol, start, end)


def test_market_download_and_validation_are_immutable(tmp_path: Path) -> None:
    fake = FakePriceProvider()
    service = MarketDataService(tmp_path, providers={"tiingo": fake})
    result = service.download(
        provider="tiingo", symbol="QQQ", start="2024-01-02", end="2024-01-05", price_policy="raw"
    )
    assert result["status"] == "DOWNLOADED"
    assert result["bars"] == 4
    assert result["zone"] == "development"
    assert result["quality"]["point_in_time_verified"] is False
    assert result["orders_enabled"] is False
    data_path = result["data_path"]
    assert isinstance(data_path, str)
    assert data_path.startswith("data/market/tiingo/")
    assert ParquetDataProvider.read(tmp_path / data_path).zone is DataZone.DEVELOPMENT
    assert service.list_datasets()["count"] == 1
    before_hash = result["dataset_hash"]
    assert service.validate_dataset(data_path)["dataset_hash"] == before_hash
    again = service.download(
        provider="tiingo", symbol="QQQ", start="2024-01-02", end="2024-01-05", price_policy="raw"
    )
    assert again["status"] == "ALREADY_EXISTS"
    assert fake.calls == 1


def test_market_download_rejects_incomplete_range_without_creating_files(tmp_path: Path) -> None:
    class Capped:
        def daily_bars(
            self, symbol: str, start: date, end: date, *, adjusted: bool
        ) -> tuple[Bar, ...]:
            return _rows(symbol, end - timedelta(days=6), end)

    service = MarketDataService(tmp_path, providers={"kis": Capped()})
    with pytest.raises(MarketDataError) as error:
        service.download(provider="kis", symbol="QQQ", start="2020-01-01", end="2024-02-01")
    assert error.value.code == "INCOMPLETE_RANGE"
    assert service.list_datasets()["count"] == 0


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (
            {"provider": "other", "symbol": "QQQ", "start": "2024-01-01", "end": "2024-01-02"},
            "UNKNOWN_PROVIDER",
        ),
        (
            {"provider": "tiingo", "symbol": "../", "start": "2024-01-01", "end": "2024-01-02"},
            "INVALID_SYMBOL",
        ),
        (
            {"provider": "tiingo", "symbol": "QQQ", "start": "2024-05-02", "end": "2024-01-02"},
            "INVALID_RANGE",
        ),
        (
            {
                "provider": "kis",
                "symbol": "QQQ",
                "start": "2024-01-01",
                "end": "2024-01-02",
                "price_policy": "total_return_adjusted",
            },
            "POLICY_UNSUPPORTED",
        ),
    ],
)
def test_market_request_validation(tmp_path: Path, payload: dict[str, str], error: str) -> None:
    service = MarketDataService(tmp_path, providers={"tiingo": FakePriceProvider()})
    with pytest.raises(MarketDataError) as raised:
        service.download(**payload)
    assert raised.value.code == error


def test_tiingo_fixed_host_token_header_adjusted_prices_and_error_sanitization() -> None:
    captured = []

    def mock(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "date": "2024-01-02T00:00:00.000Z",
                    "open": 100,
                    "high": 103,
                    "low": 99,
                    "close": 102,
                    "volume": 1000,
                    "adjOpen": 95,
                    "adjHigh": 97,
                    "adjLow": 94,
                    "adjClose": 96,
                    "adjVolume": 1120,
                }
            ],
        )

    provider = TiingoDailyProvider("test-local-credential", transport=httpx.MockTransport(mock))
    bars = provider.daily_bars("QQQ", date(2024, 1, 2), date(2024, 1, 2), adjusted=True)
    assert bars[0].open == 95
    assert bars[0].volume == 1120
    assert captured[0].url.host == "api.tiingo.com"
    assert captured[0].headers["Authorization"] == "Token test-local-credential"
    assert "test-local-credential" not in str(captured[0].url)

    failed = TiingoDailyProvider(
        "test-secret",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, text="sensitive provider error")
        ),
    )
    with pytest.raises(MarketDataError) as exc:
        failed.daily_bars("QQQ", date(2024, 1, 2), date(2024, 1, 2), adjusted=False)
    assert exc.value.code == "PROVIDER_RATE_LIMITED"
    assert "sensitive" not in str(exc.value) and "test-secret" not in str(exc.value)


def test_kis_start_boundary_is_applied_to_returned_bars(tmp_path: Path) -> None:
    conf = tmp_path / ".env"
    _env(conf)
    transport = RecordingTransport(
        [
            KISResponse(200, {"access_token": "dummy", "access_token_token_expired": "2099-01-01"}),
            KISResponse(
                200,
                {
                    "rt_cd": "0",
                    "output2": [
                        {
                            "xymd": "20241230",
                            "open": "98",
                            "high": "102",
                            "low": "97",
                            "clos": "100",
                            "tvol": "1000",
                        },
                        {
                            "xymd": "20250102",
                            "open": "101",
                            "high": "103",
                            "low": "100",
                            "clos": "102",
                            "tvol": "1100",
                        },
                    ],
                },
            ),
        ]
    )
    client = KISPaperClient(PaperKISConfig.from_env(conf), transport=transport)
    bars = client.daily_bars("AAPL", start="20250101", end="20250103")
    assert [item.timestamp.strftime("%Y%m%d") for item in bars] == ["20250102"]


def test_market_mcp_read_only_available_and_error_codes(tmp_path: Path) -> None:
    names = {tool["name"] for tool in chatgpt_tools()}
    assert {"list_market_data", "validate_market_data", "download_market_data"} <= names
    assert not any("order" in x or "credential" in x for x in names)
    adapter = create_chatgpt_sdk_adapter(project_root=tmp_path, state_dir=tmp_path / "state")

    async def check() -> None:
        result = await adapter.call_tool(
            None, CallToolRequestParams(name="list_market_data", arguments={})
        )
        assert result.is_error is False
        payload = json.loads(result.content[0].text)
        assert payload["count"] == 0 and payload["orders_enabled"] is False
        bad = await adapter.call_tool(
            None,
            CallToolRequestParams(
                name="download_market_data",
                arguments={
                    "provider": "tiingo",
                    "symbol": "QQQ",
                    "start": "2024-01-01",
                    "end": "2024-01-02",
                },
            ),
        )
        assert bad.is_error is True
        response = json.loads(bad.content[0].text)
        assert response["error_code"] == "PROVIDER_NOT_CONFIGURED"
        assert response["orders_enabled"] is False

    asyncio.run(check())


def test_market_download_rejects_symlinked_data_root(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    (tmp_path / "data").symlink_to(other, target_is_directory=True)
    service = MarketDataService(tmp_path, providers={"tiingo": FakePriceProvider()})
    with pytest.raises(MarketDataError) as exc:
        service.download(provider="tiingo", symbol="QQQ", start="2024-01-01", end="2024-01-03")
    assert exc.value.code == "DATA_PATH_UNSAFE"
    assert not list(other.rglob("*.parquet"))


def test_market_tiingo_key_in_private_dotenv_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    (tmp_path / ".env").write_text("TIINGO_API_KEY=not-a-real-key\n")
    service = MarketDataService(tmp_path)
    status = service.provider_status()
    assert status["providers"][0]["configured"] is True
    assert "not-a-real-key" not in str(status)
