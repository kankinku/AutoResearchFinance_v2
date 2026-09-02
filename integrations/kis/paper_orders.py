from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from integrations.kis.client import (
    KISPaperClient,
    KISTransport,
    _account_parts,
    _number,
    _records,
    _symbol,
)
from integrations.kis.config import PaperKISConfig


class PaperOrderError(RuntimeError):
    """Raised when a paper order cannot be safely submitted or verified."""


@dataclass(frozen=True)
class PaperOrderReceipt:
    symbol: str
    side: str
    exchange: str
    requested_quantity: int
    order_id: str


@dataclass(frozen=True)
class PaperRoundTripResult:
    status: str
    buy: PaperOrderReceipt
    filled_buy_quantity: int
    sell: PaperOrderReceipt | None
    filled_sell_quantity: int
    final_position_quantity: float | None


class KISPaperOrderClient:
    """Paper-only KIS order capability, isolated from research and read-only APIs."""

    def __init__(
        self,
        config: PaperKISConfig,
        *,
        transport: KISTransport | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        _validate_paper_endpoint(config, transport_is_injected=transport is not None)
        if not config.account_number:
            raise PaperOrderError("paper account number is required")
        self.config = config
        self._read_only = KISPaperClient(config, transport=transport, clock=clock)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep = sleeper
        self._monotonic = monotonic

    def place_market_order(
        self, symbol: str, side: str, *, quantity: int, exchange: str = "NASD"
    ) -> PaperOrderReceipt:
        symbol = _symbol(symbol)
        if side not in {"buy", "sell"}:
            raise PaperOrderError("order side must be buy or sell")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise PaperOrderError("paper orders require a positive whole-share quantity")
        exchange = exchange.strip().upper()
        if exchange not in {"NASD", "NYSE", "AMEX"}:
            raise PaperOrderError("US paper order exchange is invalid")

        cano, product = _account_parts(self.config.account_number, self.config.product_code)
        tr_id = "VTTT1002U" if side == "buy" else "VTTT1006U"
        payload = self._read_only._call(  # noqa: SLF001 - capability is intentionally composed
            "POST",
            "/uapi/overseas-stock/v1/trading/order",
            tr_id=tr_id,
            body={
                "CANO": cano,
                "ACNT_PRDT_CD": product,
                "OVRS_EXCG_CD": exchange,
                "PDNO": symbol,
                "ORD_DVSN": "01",
                "ORD_QTY": str(quantity),
                "OVRS_ORD_UNPR": "0",
                "SLL_TYPE": "" if side == "buy" else "00",
                "ORD_SVR_DVSN_CD": "0",
            },
        )
        order_id = _order_id(payload.get("output"))
        if not order_id:
            raise PaperOrderError("paper order response did not contain an order id")
        return PaperOrderReceipt(symbol, side, exchange, quantity, order_id)

    def run_buy_then_sell(
        self,
        symbol: str = "QQQ",
        *,
        quantity: int = 1,
        exchange: str = "NASD",
        timeout_seconds: float = 30.0,
        poll_seconds: float = 1.0,
    ) -> PaperRoundTripResult:
        if timeout_seconds < 0 or poll_seconds < 0:
            raise PaperOrderError("timeouts must not be negative")
        symbol = _symbol(symbol)
        initial_position = self._position_quantity(symbol, exchange=exchange)
        buy = self.place_market_order(symbol, "buy", quantity=quantity, exchange=exchange)
        filled_buy = self._wait_for_fill(buy, timeout_seconds, poll_seconds)
        if filled_buy <= 0:
            return PaperRoundTripResult("BUY_NOT_FILLED", buy, 0, None, 0, initial_position)

        sell = self.place_market_order(
            symbol, "sell", quantity=filled_buy, exchange=exchange
        )
        filled_sell = self._wait_for_fill(sell, timeout_seconds, poll_seconds)
        final_position = self._position_quantity(symbol, exchange=exchange)
        if filled_sell < filled_buy:
            status = "SELL_NOT_FILLED"
        elif abs(final_position - initial_position) > 1e-9:
            status = "NOT_FLAT"
        else:
            status = "FLAT"
        return PaperRoundTripResult(
            status,
            buy,
            filled_buy,
            sell,
            filled_sell,
            final_position,
        )

    def _wait_for_fill(
        self, receipt: PaperOrderReceipt, timeout_seconds: float, poll_seconds: float
    ) -> int:
        deadline = self._monotonic() + timeout_seconds
        while True:
            filled = self._filled_quantity(receipt)
            if filled > 0 or self._monotonic() >= deadline:
                return filled
            self._sleep(poll_seconds)

    def _filled_quantity(self, receipt: PaperOrderReceipt) -> int:
        cano, product = _account_parts(self.config.account_number, self.config.product_code)
        now = self._clock().strftime("%Y%m%d")
        payload = self._read_only._call(  # noqa: SLF001
            "GET",
            "/uapi/overseas-stock/v1/trading/inquire-ccnl",
            tr_id="VTTS3035R",
            params={
                "CANO": cano,
                "ACNT_PRDT_CD": product,
                "PDNO": "",
                "ORD_STRT_DT": now,
                "ORD_END_DT": now,
                "SLL_BUY_DVSN": "00",
                "CCLD_NCCS_DVSN": "00",
                "OVRS_EXCG_CD": "",
                "SORT_SQN": "DS",
                "ORD_DT": "",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "CTX_AREA_NK200": "",
                "CTX_AREA_FK200": "",
            },
        )
        total = 0
        for record in _records(payload.get("output")):
            if _order_id(record) != receipt.order_id:
                continue
            if str(record.get("pdno", record.get("PDNO", ""))).upper() != receipt.symbol:
                continue
            record_side = str(record.get("sll_buy_dvsn", record.get("SLL_BUY_DVSN", "")))
            expected_side = "02" if receipt.side == "buy" else "01"
            if record_side and record_side != expected_side:
                continue
            total += int(
                _number(
                    record,
                    ("ft_ccld_qty", "ft_ccld_qty2", "ccld_qty", "filled_quantity"),
                )
                or 0
            )
        return total

    def _position_quantity(self, symbol: str, *, exchange: str) -> float:
        snapshot = self._read_only.account_snapshot(exchange=exchange, currency="USD")
        for holding in snapshot.holdings:
            if holding.symbol.upper() == symbol:
                return holding.quantity
        return 0.0


def _validate_paper_endpoint(config: PaperKISConfig, *, transport_is_injected: bool) -> None:
    if config.mode not in {"", "paper", "demo"}:
        raise PaperOrderError("paper order client rejects non-paper mode")
    host = (urlparse(config.base_url).hostname or "").lower()
    if host in {"openapi.koreainvestment.com", "openapi.koreainvestment.com:9443"}:
        raise PaperOrderError(
            "paper order client rejects the live KIS endpoint; virtual endpoint required"
        )
    if not transport_is_injected and host != "openapivts.koreainvestment.com":
        raise PaperOrderError("paper order client requires the KIS virtual-trading endpoint")


def _order_id(value: object) -> str:
    if isinstance(value, Mapping):
        for key in ("ODNO", "odno", "order_id", "ORDER_ID"):
            item = value.get(key)
            if item not in (None, ""):
                return str(item)
    return ""
