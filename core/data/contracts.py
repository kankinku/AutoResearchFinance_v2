from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from core.integrity.hashes import content_hash


class DataContractError(ValueError):
    """Raised when market data violates the versioned data contract."""


class DataZone(str, Enum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    SEALED_OOS = "sealed_oos"


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DataContractError("timestamp timezone is required")
        if not self.symbol:
            raise DataContractError("symbol cannot be empty")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise DataContractError("prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise DataContractError("OHLC bounds are invalid")
        if self.volume < 0:
            raise DataContractError("volume cannot be negative")

    def record(self) -> dict[str, str | float]:
        return {
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "symbol": self.symbol,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class MarketDataSet:
    version: str
    zone: DataZone | str
    bars: tuple[Bar, ...]

    def __post_init__(self) -> None:
        if not self.version:
            raise DataContractError("dataset version cannot be empty")
        object.__setattr__(self, "zone", DataZone(self.zone))
        keys = [(bar.symbol, bar.timestamp.astimezone(timezone.utc)) for bar in self.bars]
        if len(keys) != len(set(keys)):
            raise DataContractError("duplicate symbol/timestamp bars")
        if list(keys) != sorted(keys):
            raise DataContractError("bars must be sorted by symbol and timestamp")

    @property
    def dataset_hash(self) -> str:
        zone = DataZone(self.zone)
        return content_hash(
            {
                "version": self.version,
                "zone": zone.value,
                "bars": [bar.record() for bar in self.bars],
            }
        )
