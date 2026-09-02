from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from integrations.kis.client import KISResponse
from integrations.kis.config import PaperKISConfig
from integrations.kis.paper_orders import KISPaperOrderClient, PaperOrderError


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


def _config(
    tmp_path: Path,
    *,
    mode: str = "paper",
    base_url: str = "https://paper.example",
) -> PaperKISConfig:
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(
            (
                "KIS_PAPER_APP_KEY=placeholder",
                "KIS_PAPER_APP_SECRET=placeholder",
                f"KIS_PAPER_BASE_URL={base_url}",
                "KIS_ACCOUNT_NO=12345678-01",
                "KIS_PRODUCT_CODE=01",
                f"QUANT_TRADING_MODE={mode}",
            )
        ),
        encoding="utf-8",
    )
    return PaperKISConfig.from_env(path)


def _token() -> KISResponse:
    return KISResponse(
        200,
        {"access_token": "placeholder", "access_token_token_expired": "2099-01-01"},
    )


def _account() -> KISResponse:
    return KISResponse(
        200,
        {
            "rt_cd": "0",
            "output1": [],
            "output2": {
                "ovrs_tot_evlu_amt": "10000",
                "frcr_pchs_amt": "10000",
                "frcr_buy_psbl_amt": "10000",
            },
        },
    )


def test_market_buy_uses_paper_overseas_order_contract(tmp_path: Path) -> None:
    transport = RecordingTransport(
        [_token(), KISResponse(200, {"rt_cd": "0", "output": {"ODNO": "100"}})]
    )
    client = KISPaperOrderClient(_config(tmp_path), transport=transport)

    receipt = client.place_market_order("QQQ", "buy", quantity=1)

    assert receipt.order_id == "100"
    call = transport.calls[1]
    assert call["method"] == "POST"
    assert call["url"].endswith("/uapi/overseas-stock/v1/trading/order")
    assert call["headers"]["tr_id"] == "VTTT1002U"
    assert call["body"] == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",
        "PDNO": "QQQ",
        "ORD_DVSN": "01",
        "ORD_QTY": "1",
        "OVRS_ORD_UNPR": "0",
        "SLL_TYPE": "",
        "ORD_SVR_DVSN_CD": "0",
    }


def test_round_trip_sells_only_the_confirmed_buy_fill(tmp_path: Path) -> None:
    transport = RecordingTransport(
        [
            _token(),
            _account(),
            KISResponse(200, {"rt_cd": "0", "output": {"ODNO": "100"}}),
            KISResponse(
                200,
                {
                    "rt_cd": "0",
                    "output": [
                        {
                            "odno": "100",
                            "pdno": "QQQ",
                            "sll_buy_dvsn": "02",
                            "ft_ccld_qty": "1",
                        }
                    ],
                },
            ),
            KISResponse(200, {"rt_cd": "0", "output": {"ODNO": "101"}}),
            KISResponse(
                200,
                {
                    "rt_cd": "0",
                    "output": [
                        {
                            "odno": "101",
                            "pdno": "QQQ",
                            "sll_buy_dvsn": "01",
                            "ft_ccld_qty": "1",
                        }
                    ],
                },
            ),
            _account(),
        ]
    )
    client = KISPaperOrderClient(
        _config(tmp_path),
        transport=transport,
        clock=lambda: datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    )

    result = client.run_buy_then_sell("QQQ", quantity=1, timeout_seconds=1)

    assert result.status == "FLAT"
    assert result.buy.order_id == "100"
    assert result.sell is not None and result.sell.order_id == "101"
    order_calls = [
        call
        for call in transport.calls
        if call["url"].endswith("/uapi/overseas-stock/v1/trading/order")
    ]
    assert order_calls[1]["headers"]["tr_id"] == "VTTT1006U"
    assert order_calls[1]["body"]["ORD_QTY"] == "1"


def test_round_trip_does_not_sell_when_buy_is_unfilled(tmp_path: Path) -> None:
    transport = RecordingTransport(
        [
            _token(),
            _account(),
            KISResponse(200, {"rt_cd": "0", "output": {"ODNO": "100"}}),
            KISResponse(200, {"rt_cd": "0", "output": []}),
        ]
    )
    client = KISPaperOrderClient(_config(tmp_path), transport=transport, sleeper=lambda _: None)

    result = client.run_buy_then_sell("QQQ", quantity=1, timeout_seconds=0)

    assert result.status == "BUY_NOT_FILLED"
    assert result.sell is None
    assert not any(call["headers"].get("tr_id") == "VTTT1006U" for call in transport.calls)


def test_live_configuration_is_rejected_before_order_request(tmp_path: Path) -> None:
    config = _config(tmp_path, mode="paper", base_url="https://openapi.koreainvestment.com:9443")
    transport = RecordingTransport([])

    with pytest.raises(PaperOrderError, match="virtual"):
        KISPaperOrderClient(config, transport=transport)

    assert transport.calls == []
