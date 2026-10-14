"""S6 pinned, curated algebraic rule variants with known historical provenance.

These are original small reference calculations, NOT copied third-party code or
replications of empirical paper profits. No new/fictional DOI is introduced.
"""
from __future__ import annotations

from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.models import CANONICAL_FORMULAS, IndicatorCandidate
from research.indicator_engine.seed import ACADEMIC_PAPERS


def _entry(signal_id: str, calculator: str, fields: tuple[str, ...],
           lookback: int, family: str) -> IndicatorCandidate:
    return IndicatorCandidate.model_validate({
        "signal_id": signal_id,
        "paper_doi": ACADEMIC_PAPERS[0].doi,
        "calculator": calculator,
        "family": family,
        "role": "entry",
        "required_fields": fields,
        "lookback": lookback,
        "formula": CANONICAL_FORMULAS[calculator],
        "scope": "single_asset", "status": "PROPOSED",
    })


S6_SIGNALS: tuple[IndicatorCandidate, ...] = (
    _entry("sma_pullback_20", "sma_pullback", ("close",), 20, "mean_reversion"),
    _entry("dual_sma_trend_50", "dual_sma_trend", ("close",), 50, "trend"),
    _entry("ema_direction_20", "ema_direction", ("close",), 20, "trend"),
    _entry("range_low_reclaim_20", "range_low_reclaim", ("low", "close"), 20, "breakout_retest"),
)


def seed_s6_references(catalog: ResearchCatalog) -> None:
    """Append proposed signals only. Approval is independent and explicit."""
    for signal in S6_SIGNALS:
        try:
            old = catalog.get_indicator(signal.signal_id)
        except ResearchCatalogError:
            catalog.add_indicator(signal)
        else:
            # Existing VERIFIED records are immutable across S6 updates.
            if old.status == "PROPOSED" and old != signal:
                raise ResearchCatalogError("S6 rule identity conflict")
            if old.status != "PROPOSED" and old.model_copy(update={"status": "PROPOSED"}) != signal:
                raise ResearchCatalogError("S6 verified rule version conflict")
