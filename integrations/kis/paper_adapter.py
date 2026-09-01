from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PaperApproval:
    champion_hash: str
    validated: bool
    expires_at: datetime


@dataclass(frozen=True)
class PaperFill:
    symbol: str
    side: str
    quantity: float
    price: float

    @property
    def notional(self) -> float:
        return self.quantity * self.price


class PaperTradingAdapter:
    """Deterministic paper broker; it never calls the live KIS order API."""

    def __init__(self, champion_hash: str, *, initial_cash: float) -> None:
        if not champion_hash or initial_cash <= 0:
            raise ValueError("champion hash and positive initial cash are required")
        self.champion_hash = champion_hash
        self.cash = initial_cash
        self.positions: dict[str, float] = {}
        self._enabled = False

    def enable(self, approval: PaperApproval) -> None:
        if approval.champion_hash != self.champion_hash:
            raise PermissionError("paper approval champion hash does not match")
        if not approval.validated:
            raise PermissionError("paper validation is required")
        if approval.expires_at.tzinfo is None or approval.expires_at <= datetime.now(timezone.utc):
            raise PermissionError("paper approval is expired")
        self._enabled = True

    def submit_order(self, symbol: str, side: str, *, quantity: float, price: float) -> PaperFill:
        if not self._enabled:
            raise PermissionError("paper trading is not enabled")
        if not symbol or side not in {"buy", "sell"} or quantity <= 0 or price <= 0:
            raise ValueError("symbol, side, quantity, and price are invalid")
        fill = PaperFill(symbol, side, quantity, price)
        if side == "buy":
            if fill.notional > self.cash:
                raise ValueError("insufficient paper cash")
            self.cash -= fill.notional
            self.positions[symbol] = self.positions.get(symbol, 0.0) + quantity
        else:
            held = self.positions.get(symbol, 0.0)
            if quantity > held:
                raise ValueError("insufficient paper position")
            self.cash += fill.notional
            self.positions[symbol] = held - quantity
        return fill
