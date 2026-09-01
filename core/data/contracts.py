from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite

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
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
        }


@dataclass(frozen=True)
class SeriesObservation:
    """A point-in-time observation for prices, macro data, or derived series."""

    series_id: str
    timestamp: datetime
    value: float
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DataContractError("series timestamp timezone is required")
        if self.available_at is not None and (
            self.available_at.tzinfo is None or self.available_at.utcoffset() is None
        ):
            raise DataContractError("series availability timezone is required")
        if self.available_at is not None and self.available_at < self.timestamp:
            raise DataContractError("series availability cannot precede observation")
        if not self.series_id:
            raise DataContractError("series_id cannot be empty")
        if not isfinite(self.value):
            raise DataContractError("series value must be finite")

    def record(self) -> dict[str, str | float]:
        return {
            "series_id": self.series_id,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "value": float(self.value),
            "available_at": (
                self.available_at.astimezone(timezone.utc).isoformat()
                if self.available_at is not None
                else ""
            ),
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


@dataclass(frozen=True)
class SeriesDataSet:
    """Versioned external time-series data with explicit availability metadata."""

    version: str
    zone: DataZone | str
    observations: tuple[SeriesObservation, ...]

    def __post_init__(self) -> None:
        if not self.version:
            raise DataContractError("series dataset version cannot be empty")
        object.__setattr__(self, "zone", DataZone(self.zone))
        keys = [
            (observation.series_id, observation.timestamp.astimezone(timezone.utc))
            for observation in self.observations
        ]
        if len(keys) != len(set(keys)):
            raise DataContractError("duplicate series/timestamp observations")
        if list(keys) != sorted(keys):
            raise DataContractError("observations must be sorted by series and timestamp")

    @property
    def dataset_hash(self) -> str:
        return content_hash(
            {
                "version": self.version,
                "zone": DataZone(self.zone).value,
                "observations": [observation.record() for observation in self.observations],
            }
        )
