"""P0 academic indicator research: fail-closed paper catalog and hypothesis planning.

No broker access, no automatic production FeatureRegistry registration.
"""

from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.composer import compose_hypotheses
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import (
    calculate_signal,
    verify_signal_on_synthetic_prices,
)

__all__ = (
    "ResearchCatalog",
    "ResearchCatalogError",
    "calculate_signal",
    "compose_hypotheses",
    "seed_approved_references",
    "verify_signal_on_synthetic_prices",
)
