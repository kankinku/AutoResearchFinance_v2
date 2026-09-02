from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from core.data.contracts import Bar
from integrations.kis.config import PaperKISConfig

_PAPER_REQUEST_INTERVAL_SECONDS = 1.1


class KISTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        body: dict[str, str] | None = None,
    ) -> KISResponse: ...


@dataclass(frozen=True)
class KISResponse:
    status_code: int
    payload: dict[str, Any]


class KISAPIError(RuntimeError):
    def __init__(
        self, status_code: int, code: str = "KIS_ERROR", message: str | None = None
    ) -> None:
        detail = f": {message}" if message else ""
        super().__init__(f"KIS request failed ({status_code}, {code}){detail}")
        self.status_code = status_code
        self.code = code
        self.message = message or ""


@dataclass(frozen=True)
class KISQuote:
    symbol: str
    exchange: str
    last_price: float
    captured_at: str


@dataclass(frozen=True)
class KISHolding:
    symbol: str
    quantity: float
    market_value: float
    profit_loss: float


@dataclass(frozen=True)
class KISAccountSnapshot:
    account_number: str
    equity: float
    cash: float
    buying_power: float
    holdings: tuple[KISHolding, ...]
    captured_at: str


class URLTransport:
    def __init__(self, *, timeout: float = 20.0) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        body: dict[str, str] | None = None,
    ) -> KISResponse:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=encoded, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content = response.read().decode("utf-8")
                payload = json.loads(content)
                return KISResponse(response.status, payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            status = getattr(exc, "code", 0) or 0
            raise KISAPIError(int(status), "transport") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KISAPIError(0, "invalid_response") from exc


class KISPaperClient:
    """Read-only paper KIS client for US stocks and ETFs."""

    def __init__(
        self,
        config: PaperKISConfig,
        *,
        transport: KISTransport | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        transport_was_injected = transport is not None
        self._transport = transport or URLTransport()
        self._throttle_enabled = not transport_was_injected
        self._last_request_at: float | None = None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token = ""
        self._token_expires_at = datetime.min.replace(tzinfo=timezone.utc)

    def quote(self, symbol: str, *, exchange: str = "NAS") -> KISQuote:
        symbol = _symbol(symbol)
        exchange = _exchange(exchange)
        payload = self._call(
            "GET",
            "/uapi/overseas-price/v1/quotations/price",
            tr_id="HHDFS00000300",
            params={"AUTH": "", "EXCD": exchange, "SYMB": symbol},
        )
        output = _mapping(payload.get("output"))
        last = _first_number(output, ("last", "last_pr", "ovrs_nmix_prpr", "stck_prpr"))
        if last is None:
            raise KISAPIError(200, "quote_missing_price")
        return KISQuote(symbol, exchange, last, self._clock().isoformat())

    def health(self) -> dict[str, Any]:
        self._access_token()
        return {"status": "ONLINE", "mode": "paper", "checked_at": self._clock().isoformat()}

    def daily_bars(
        self, symbol: str, *, start: str, end: str, exchange: str = "NAS"
    ) -> tuple[Bar, ...]:
        symbol = _symbol(symbol)
        exchange = _exchange(exchange)
        _date(start)
        _date(end)
        payload = self._call(
            "GET",
            "/uapi/overseas-price/v1/quotations/dailyprice",
            tr_id="HHDFS76240000",
            params={
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": symbol,
                "GUBN": "0",
                "BYMD": end,
                "MODP": "0",
            },
        )
        bars: list[Bar] = []
        for record in _records(payload.get("output2")):
            date = str(_first_value(record, ("xymd", "stck_bsop_date", "date")) or "")
            if not date:
                continue
            opening = _required_number(record, ("open", "ovrs_nmix_oprc", "stck_oprc"), "open")
            high = _required_number(record, ("high", "ovrs_nmix_hgpr", "stck_hgpr"), "high")
            low = _required_number(record, ("low", "ovrs_nmix_lwpr", "stck_lwpr"), "low")
            close = _required_number(
                record,
                ("clos", "close", "ovrs_nmix_prpr", "stck_prpr"),
                "close",
            )
            volume = _number(record, ("tvol", "acml_vol", "volume")) or 0.0
            timestamp = datetime.strptime(date, "%Y%m%d").replace(tzinfo=timezone.utc)
            bars.append(Bar(timestamp, symbol, opening, high, low, close, volume))
        return tuple(sorted(bars, key=lambda bar: bar.timestamp))

    def account_snapshot(
        self, *, exchange: str = "NASD", currency: str = "USD"
    ) -> KISAccountSnapshot:
        exchange = exchange.strip().upper()
        currency = currency.strip().upper()
        if exchange not in {"NASD", "NAS", "NYS", "AMS"}:
            raise ValueError("US account exchange is invalid")
        if currency != "USD":
            raise ValueError("paper dashboard supports USD account snapshots only")
        cano, product = _account_parts(self.config.account_number, self.config.product_code)
        payload = self._call(
            "GET",
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            tr_id="VTTS3012R",
            params={
                "CANO": cano,
                "ACNT_PRDT_CD": product,
                "OVRS_EXCG_CD": exchange,
                "TR_CRCY_CD": currency,
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        summary = _first_record(payload.get("output2"))
        holdings = tuple(
            KISHolding(
                symbol=str(_first_value(record, ("ovrs_pdno", "pdno", "symbol")) or ""),
                quantity=_number(record, ("ovrs_cblc_qty", "ord_psbl_qty", "quantity")) or 0.0,
                market_value=_number(record, ("ovrs_evlu_amt", "market_value")) or 0.0,
                profit_loss=_number(record, ("frcr_evlu_pfls_amt", "profit_loss")) or 0.0,
            )
            for record in _records(payload.get("output1"))
            if _first_value(record, ("ovrs_pdno", "pdno", "symbol"))
        )
        equity = _number(summary, ("ovrs_tot_evlu_amt", "tot_evlu_pfls_amt", "equity"))
        cash = _number(summary, ("frcr_pchs_amt", "cash", "tot_frcr_cblc_smtl"))
        buying_power = _number(summary, ("frcr_buy_psbl_amt", "buying_power"))
        if equity is None or cash is None or buying_power is None:
            present_payload = self._call(
                "GET",
                "/uapi/overseas-stock/v1/trading/inquire-present-balance",
                tr_id="VTRP6504R",
                params={
                    "CANO": cano,
                    "ACNT_PRDT_CD": product,
                    "WCRC_FRCR_DVSN_CD": "02",
                    "NATN_CD": "840",
                    "TR_MKET_CD": "00",
                    "INQR_DVSN_CD": "00",
                },
            )
            present = _first_record(present_payload.get("output3"))
            equity = equity if equity is not None else _number(
                present,
                ("frcr_evlu_tota", "tot_asst_amt", "evlu_amt_smtl"),
            )
            cash = cash if cash is not None else _number(
                present,
                ("frcr_use_psbl_amt", "tot_frcr_cblc_smtl", "cash"),
            )
            buying_power = buying_power if buying_power is not None else _number(
                present,
                ("ustl_buy_amt_smtl", "frcr_use_psbl_amt", "buying_power"),
            )
        return KISAccountSnapshot(
            account_number=_mask_account(self.config.account_number),
            equity=_required_number_from_value(equity, "equity"),
            cash=_required_number_from_value(cash, "cash"),
            buying_power=_required_number_from_value(buying_power, "buying_power"),
            holdings=holdings,
            captured_at=self._clock().isoformat(),
        )

    def _access_token(self) -> str:
        now = self._clock()
        if self._token and now + timedelta(seconds=30) < self._token_expires_at:
            return self._token
        response = self._request(
            "POST",
            f"{self.config.base_url}/oauth2/tokenP",
            headers={"content-type": "application/json"},
            body={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
        )
        if response.status_code != 200:
            raise KISAPIError(response.status_code, "token_http")
        token = response.payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise KISAPIError(response.status_code, "token_missing")
        self._token = token
        self._token_expires_at = _parse_expiry(
            response.payload.get("access_token_token_expired"), now
        )
        return token

    def _call(
        self,
        method: str,
        path: str,
        *,
        tr_id: str,
        params: dict[str, str] | None = None,
        body: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        token = self._access_token()
        response = self._request(
            method,
            f"{self.config.base_url}{path}",
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {token}",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
                "tr_id": tr_id,
                "custtype": "P",
            },
            params=params,
            body=body,
        )
        payload = response.payload
        if response.status_code != 200 or payload.get("rt_cd") not in {None, "0"}:
            code = payload.get("msg_cd")
            message = payload.get("msg1")
            raise KISAPIError(
                response.status_code,
                str(code) if code else "api_error",
                str(message) if message else None,
            )
        return payload

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        body: dict[str, str] | None = None,
    ) -> KISResponse:
        if self._throttle_enabled:
            now = time.monotonic()
            if self._last_request_at is not None:
                remaining = _PAPER_REQUEST_INTERVAL_SECONDS - (now - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request_at = time.monotonic()
        return self._transport.request(
            method,
            url,
            headers=headers,
            params=params,
            body=body,
        )


def _symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    valid_characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
    if not normalized or any(char not in valid_characters for char in normalized):
        raise ValueError("US symbol is invalid")
    return normalized


def _exchange(exchange: str) -> str:
    normalized = exchange.strip().upper()
    if normalized not in {"NAS", "NYS", "AMS"}:
        raise ValueError("US exchange must be NAS, NYS, or AMS")
    return normalized


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _records(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, Mapping):
        return (_mapping(value),)
    if isinstance(value, list):
        return tuple(_mapping(item) for item in value if isinstance(item, Mapping))
    return ()


def _first_record(value: object) -> Mapping[str, object]:
    return _records(value)[0] if _records(value) else {}


def _first_value(output: Mapping[str, object], names: tuple[str, ...]) -> object | None:
    for name in names:
        if output.get(name) not in (None, ""):
            return output[name]
    return None


def _first_number(output: Mapping[str, object], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = output.get(name)
        if value is None or value == "":
            continue
        try:
            return float(str(value))
        except (TypeError, ValueError):
            continue
    return None


def _number(output: Mapping[str, object], names: tuple[str, ...]) -> float | None:
    value = _first_value(output, names)
    try:
        return float(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _required_number(output: Mapping[str, object], names: tuple[str, ...], label: str) -> float:
    value = _number(output, names)
    return _required_number_from_value(value, label)


def _required_number_from_value(value: float | None, label: str) -> float:
    if value is None:
        raise KISAPIError(200, f"missing_{label}")
    return value


def _date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("date must use YYYYMMDD") from exc
    return value


def _account_parts(account: str, product: str) -> tuple[str, str]:
    digits = "".join(char for char in account if char.isdigit())
    if len(digits) < 8:
        raise ValueError("KIS_ACCOUNT_NO must contain at least 8 digits")
    cano = digits[:8]
    account_product = digits[8:10] if len(digits) >= 10 else product
    if len(account_product) != 2 or not account_product.isdigit():
        raise ValueError("KIS_PRODUCT_CODE must contain two digits")
    return cano, account_product


def _mask_account(account: str) -> str:
    digits = "".join(char for char in account if char.isdigit())
    if len(digits) < 10:
        return "******"
    return f"******{digits[-4:-2]}-{digits[-2:]}"


def _parse_expiry(value: object, now: datetime) -> datetime:
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
            except ValueError:
                continue
    return now + timedelta(hours=1)
