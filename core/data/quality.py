"""Point-in-time declaration assessment; never certifies historical vendor accuracy."""

from __future__ import annotations

from dataclasses import dataclass

from core.data.contracts import MarketDataSet


@dataclass(frozen=True)
class MarketDataQuality:
    status: str
    issues: tuple[str, ...]
    point_in_time_verified: bool = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "issues": list(self.issues),
            "point_in_time_verified": self.point_in_time_verified,
        }


def market_data_quality(dataset: MarketDataSet) -> MarketDataQuality:
    """Report source declarations without promoting unverified data to validated OOS."""
    issues: list[str] = []
    provenance = dataset.provenance
    if not dataset.bars:
        issues.append("empty_market_data")
    if provenance is None:
        issues.append("provenance_missing")
    else:
        if provenance.revision_policy != "as_of":
            issues.append("revisions_not_as_of")
        if provenance.universe_policy == "current_constituents":
            issues.append("survivorship_risk")
        if provenance.universe_policy != "single_symbol" and not provenance.includes_delisted:
            issues.append("delisted_assets_missing")
        if provenance.corporate_action_policy == "raw" or not provenance.corporate_action_reference:
            issues.append("corporate_action_adjustment_unverified")
    return MarketDataQuality("UNVERIFIED" if issues else "DECLARED_POINT_IN_TIME", tuple(issues))
