"""Bounded, separately registered fast re-entry research hypotheses.

These are explicit QQQ transport hypotheses, not reproductions of the original
multi-asset futures/stock-index literature and never automatic promotion.
"""

from __future__ import annotations

from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.models import IndicatorCandidate

# Fixed before evaluation: ~3- and ~6-month binary time-series entry,
# alongside 10/20-day simple-trend entry gates. No free-form optimizer.
REENTRY_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("time_series_momentum_63", "sma_direction_10"),
    ("time_series_momentum_126", "sma_direction"),
)

_VARIANTS: tuple[tuple[str, str, int], ...] = (
    ("time_series_momentum_63", "time_series_momentum", 63),
    ("time_series_momentum_126", "time_series_momentum", 126),
    ("sma_direction_10", "sma_direction", 10),
)


def register_reentry_challengers(catalog: ResearchCatalog) -> tuple[IndicatorCandidate, ...]:
    """Register unverified research options without modifying original seed.

    Caller must independently verify/register each candidate's math. Never
    convert a proposal into VERIFIED simply by inserting it into the catalog.
    """
    registered: list[IndicatorCandidate] = []
    for signal_id, parent, lookback in _VARIANTS:
        reference = catalog.get_indicator(parent)
        expected = reference.model_copy(update={
            "signal_id": signal_id,
            "lookback": lookback,
            "status": "PROPOSED",
        })
        try:
            current = catalog.get_indicator(signal_id)
        except ResearchCatalogError:
            catalog.add_indicator(expected)
            current = expected
        if current.model_copy(update={"status": "PROPOSED"}) != expected:
            raise ResearchCatalogError("reentry challenger identity conflicts with preregistration")
        registered.append(current)
    return tuple(registered)
