from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from integrations.kis.client import KISPaperClient, KISResponse
from integrations.kis.config import KISConfigError, PaperKISConfig


class RecordingTransport:
    def __init__(self, responses: list[KISResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        body: dict[str, str] | None = None,
    ) -> KISResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": dict(params or {}),
                "body": dict(body or {}),
            }
        )
        return next(self.responses)


def _env(path: Path, *, mode: str = "paper") -> None:
    path.write_text(
        "\n".join(
            (
                "KIS_PAPER_APP_KEY=paper-key",
                "KIS_PAPER_APP_SECRET=paper-secret",
                "KIS_PAPER_BASE_URL=https://paper.example",
                "KIS_ACCOUNT_NO=12345678-01",
                "KIS_PRODUCT_CODE=01",
                f"QUANT_TRADING_MODE={mode}",
            )
        ),
        encoding="utf-8",
    )


def test_paper_config_loads_dotenv_without_exposing_secret_in_repr(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _env(env_path)

    config = PaperKISConfig.from_env(env_path)

    assert config.base_url == "https://paper.example"
    assert config.account_number == "12345678-01"
    assert "paper-secret" not in repr(config)


def test_paper_config_rejects_live_mode(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _env(env_path, mode="live")

    with pytest.raises(KISConfigError, match="paper"):
        PaperKISConfig.from_env(env_path)


def test_paper_config_requires_credentials(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("QUANT_TRADING_MODE=paper\n", encoding="utf-8")

    with pytest.raises(KISConfigError, match="KIS_PAPER_APP_KEY"):
        PaperKISConfig.from_env(env_path)


def test_client_authenticates_and_maps_official_quote_contract(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _env(env_path)
    transport = RecordingTransport(
        [
            KISResponse(
                200,
                {
                    "access_token": "bearer-secret",
                    "access_token_token_expired": "2099-01-01 00:00:00",
                },
            ),
            KISResponse(200, {"rt_cd": "0", "output": {"last": "123.45"}}),
        ]
    )
    client = KISPaperClient(PaperKISConfig.from_env(env_path), transport=transport)

    quote = client.quote("AAPL", exchange="NAS")

    assert quote.symbol == "AAPL"
    assert quote.exchange == "NAS"
    assert quote.last_price == pytest.approx(123.45)
    assert transport.calls[0]["url"].endswith("/oauth2/tokenP")
    assert transport.calls[1]["url"].endswith("/uapi/overseas-price/v1/quotations/price")
    assert transport.calls[1]["headers"]["tr_id"] == "HHDFS00000300"
    assert transport.calls[1]["params"] == {"AUTH": "", "EXCD": "NAS", "SYMB": "AAPL"}
    assert "bearer-secret" not in repr(quote)


def test_token_is_cached_for_multiple_read_only_calls(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _env(env_path)
    transport = RecordingTransport(
        [
            KISResponse(200, {"access_token": "token", "access_token_token_expired": "2099-01-01"}),
            KISResponse(200, {"rt_cd": "0", "output": {"last": "1"}}),
            KISResponse(200, {"rt_cd": "0", "output": {"last": "2"}}),
        ]
    )
    client = KISPaperClient(PaperKISConfig.from_env(env_path), transport=transport)

    client.quote("AAPL")
    client.quote("MSFT")

    assert sum(call["url"].endswith("/oauth2/tokenP") for call in transport.calls) == 1


def test_client_maps_daily_bars_using_official_period_price_contract(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _env(env_path)
    transport = RecordingTransport(
        [
            KISResponse(200, {"access_token": "token", "access_token_token_expired": "2099-01-01"}),
            KISResponse(
                200,
                {
                    "rt_cd": "0",
                    "output2": [
                        {"xymd": "20250102", "open": "101", "high": "103", "low": "100", "clos": "102", "tvol": "1200"},
                        {"xymd": "20250101", "open": "99", "high": "101", "low": "98", "clos": "100", "tvol": "1100"},
                    ],
                },
            ),
        ]
    )
    client = KISPaperClient(PaperKISConfig.from_env(env_path), transport=transport)

    bars = client.daily_bars("AAPL", start="20250101", end="20250102", exchange="NAS")

    assert [bar.timestamp.strftime("%Y%m%d") for bar in bars] == ["20250101", "20250102"]
    assert [bar.close for bar in bars] == [100.0, 102.0]
    assert transport.calls[1]["headers"]["tr_id"] == "HHDFS76240000"
    assert transport.calls[1]["params"]["GUBN"] == "0"


def test_client_maps_read_only_account_snapshot(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    _env(env_path)
    transport = RecordingTransport(
        [
            KISResponse(200, {"access_token": "token", "access_token_token_expired": "2099-01-01"}),
            KISResponse(
                200,
                {
                    "rt_cd": "0",
                    "output1": [{"ovrs_pdno": "AAPL", "ovrs_cblc_qty": "2", "ovrs_evlu_amt": "400", "frcr_evlu_pfls_amt": "10"}],
                    "output2": {"ovrs_tot_evlu_amt": "10000", "frcr_pchs_amt": "9500", "frcr_buy_psbl_amt": "500"},
                },
            ),
        ]
    )
    client = KISPaperClient(PaperKISConfig.from_env(env_path), transport=transport)

    account = client.account_snapshot()

    assert account.equity == pytest.approx(10000)
    assert account.cash == pytest.approx(9500)
    assert account.buying_power == pytest.approx(500)
    assert account.holdings[0].symbol == "AAPL"
    assert account.holdings[0].quantity == pytest.approx(2)
    assert account.account_number == "******78-01"
    assert transport.calls[1]["headers"]["tr_id"] == "VTTS3012R"
