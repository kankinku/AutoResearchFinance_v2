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
        # DataZone is a string Enum: a decoded "sealed_oos" compares equal
        # as a dictionary key but fails identity checks. Canonicalize BEFORE
        # checking capability, never after dispatch.
        try:
            target = DataZone(zone)
        except (TypeError, ValueError) as exc:
            raise DataAccessDenied("invalid data zone") from exc
        if role == "research" and target is not DataZone.DEVELOPMENT:
            raise DataAccessDenied("research role can read development data only")
        if target is DataZone.VALIDATION and role not in {"promotion_validation", "promotion_gate"}:
            raise DataAccessDenied("validation data requires promotion validation capability")
        if target is DataZone.SEALED_OOS and role != "promotion_gate":
            raise DataAccessDenied("sealed OOS data requires promotion gate capability")
        selected = {
            DataZone.DEVELOPMENT: self.development,
            DataZone.VALIDATION: self.validation,
            DataZone.SEALED_OOS: self.sealed_oos,
        }[target]
        if selected.zone is not target:
            raise DataAccessDenied("selected dataset zone mismatch")
        return selected
