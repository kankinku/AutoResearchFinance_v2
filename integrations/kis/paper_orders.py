from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from integrations.kis.client import (
    KISAPIError,
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


@dataclass(frozen=True)
class _OrderProgress:
    filled: int
    pending: int | None


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
        buy_progress, buy_settled = self._settle_order(buy, timeout_seconds, poll_seconds)
        filled_buy = buy_progress.filled
        if not buy_settled:
            return PaperRoundTripResult("UNSETTLED", buy, filled_buy, None, 0, None)

        buy_position = self._position_quantity(symbol, exchange=exchange)
        if abs(buy_position - initial_position - filled_buy) > 1e-9:
            return PaperRoundTripResult(
                "UNSETTLED", buy, filled_buy, None, 0, buy_position
            )
        if filled_buy == 0:
            return PaperRoundTripResult(
                "BUY_NOT_FILLED", buy, 0, None, 0, buy_position
            )

        sell = self.place_market_order(
            symbol, "sell", quantity=filled_buy, exchange=exchange
        )
        sell_progress, sell_settled = self._settle_order(sell, timeout_seconds, poll_seconds)
        filled_sell = sell_progress.filled
        if not sell_settled:
            return PaperRoundTripResult(
                "UNSETTLED", buy, filled_buy, sell, filled_sell, None
            )
        final_position = self._position_quantity(symbol, exchange=exchange)
        if filled_sell < filled_buy:
            status = "SELL_NOT_FILLED"
        elif abs(final_position - initial_position) > 1e-9:
            status = "NOT_FLAT"
        else:
            status = "FLAT"
        return PaperRoundTripResult(
            status, buy, filled_buy, sell, filled_sell, final_position,
        )

    def _settle_order(
        self, receipt: PaperOrderReceipt, timeout_seconds: float, poll_seconds: float
    ) -> tuple[_OrderProgress, bool]:
        progress = self._wait_for_fill(receipt, timeout_seconds, poll_seconds)
        if progress.pending == 0 or (
            progress.filled == receipt.requested_quantity and progress.pending is None
        ):
            return progress, True

        # A partial or not-yet-visible fill cannot trigger an opposite order.
        # A successful cancel response alone is not proof of cancellation.
        try:
            self._cancel_remaining(receipt)
        except KISAPIError:
            return progress, False
        deadline = self._monotonic() + timeout_seconds
        while True:
            progress = self._order_progress(receipt)
            if progress.pending == 0 or (
                progress.filled == receipt.requested_quantity
                and progress.pending is None
            ):
                return progress, True
            if self._monotonic() >= deadline:
                return progress, False
            self._sleep(poll_seconds)

    def _cancel_remaining(self, receipt: PaperOrderReceipt) -> None:
        cano, product = _account_parts(self.config.account_number, self.config.product_code)
        result = self._read_only._call(  # noqa: SLF001 - paper-only capability
            "POST",
            "/uapi/overseas-stock/v1/trading/order-rvsecncl",
            tr_id="VTTT1004U",
            body={
                "CANO": cano,
                "ACNT_PRDT_CD": product,
                "OVRS_EXCG_CD": receipt.exchange,
                "PDNO": receipt.symbol,
                "ORGN_ODNO": receipt.order_id,
                "RVSE_CNCL_DVSN_CD": "02",
                "ORD_QTY": "0",
                "OVRS_ORD_UNPR": "0",
                "QTY_ALL_ORD_YN": "Y",
                "MGCO_APTM_ODNO": "",
                "ORD_SVR_DVSN_CD": "0",
            },
        )
        if result.get("rt_cd") != "0":
            raise PaperOrderError("paper order cancel was not acknowledged")

    def _wait_for_fill(
        self, receipt: PaperOrderReceipt, timeout_seconds: float, poll_seconds: float
    ) -> _OrderProgress:
        deadline = self._monotonic() + timeout_seconds
        while True:
            progress = self._order_progress(receipt)
            if (
                progress.filled > 0
                or progress.pending == 0
                or self._monotonic() >= deadline
            ):
                return progress
            self._sleep(poll_seconds)

    def _order_progress(self, receipt: PaperOrderReceipt) -> _OrderProgress:
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
        fills: list[int] = []
        remaining: list[int | None] = []
        for record in _records(payload.get("output")):
            if _order_id(record) != receipt.order_id:
                continue
            if str(record.get("pdno", record.get("PDNO", ""))).upper() != receipt.symbol:
                continue
            record_side = str(record.get("sll_buy_dvsn", record.get("SLL_BUY_DVSN", "")))
            expected_side = "02" if receipt.side == "buy" else "01"
            if record_side != expected_side:
                continue
            filled = _number(
                record, ("ft_ccld_qty", "ft_ccld_qty2", "ccld_qty", "filled_quantity")
            )
            pending = _number(record, ("nccs_qty", "NCCS_QTY", "unfilled_quantity"))
            if (
                filled is None or filled < 0 or not filled.is_integer()
                or (pending is not None and (pending < 0 or not pending.is_integer()))
            ):
                raise PaperOrderError("unverifiable paper order quantities")
            fills.append(int(filled))
            remaining.append(int(pending) if pending is not None else None)

        # Inquiry responses may repeat cumulative rows. Summing them would
        # fabricate extra fills and could lead to an unsafe opposite order.
        filled_count = max(fills, default=0)
        outstanding = (
            max(item for item in remaining if item is not None)
            if remaining and all(item is not None for item in remaining)
            else None
        )
        if (
            filled_count > receipt.requested_quantity
            or (
                outstanding is not None
                and filled_count + outstanding > receipt.requested_quantity
            )
        ):
            raise PaperOrderError("paper order fill totals exceed requested quantity")
        return _OrderProgress(filled_count, outstanding)

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
