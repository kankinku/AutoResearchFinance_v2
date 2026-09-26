from __future__ import annotations

from dataclasses import dataclass

from core.data.contracts import DataZone, MarketDataSet


class DataAccessDenied(PermissionError):
    """Raised when a caller lacks a data-zone capability."""


@dataclass(frozen=True)
class InMemoryDataProvider:
    development: MarketDataSet
    validation: MarketDataSet
    sealed_oos: MarketDataSet

    def read(self, zone: DataZone, *, role: str) -> MarketDataSet:
        if role == "research" and zone is not DataZone.DEVELOPMENT:
            raise DataAccessDenied("research role can read development data only")
        if zone is DataZone.VALIDATION and role not in {"promotion_validation", "promotion_gate"}:
            raise DataAccessDenied("validation data requires promotion validation capability")
        if zone is DataZone.SEALED_OOS and role != "promotion_gate":
            raise DataAccessDenied("sealed OOS data requires promotion gate capability")
        return {
            DataZone.DEVELOPMENT: self.development,
            DataZone.VALIDATION: self.validation,
            DataZone.SEALED_OOS: self.sealed_oos,
        }[zone]
