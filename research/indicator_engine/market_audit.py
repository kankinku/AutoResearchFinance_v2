"""Fail-closed PIT readiness and *same-source* price-reference diagnostics.

This intentionally CANNOT certify an independent benchmark, dividend-adjusted
return, point-in-time vendor vintage or forward-looking publication timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from core.costs.model import CostModel
from core.costs.slippage import SlippageModel
from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError

_REFERENCE_COST = CostModel("academic-market-reference-v1", 1.0, 2.0, SlippageModel(5.0))


@dataclass(frozen=True)
class DevelopmentMarketReference:
    dataset_hash: str
    reference_hash: str
    symbol: str
    initial_cash: float
    price_only_marked_equity: float
    purchase_cost: float
    blockers: tuple[str, ...]
    status: Literal["DEVELOPMENT_REFERENCE_ONLY"] = "DEVELOPMENT_REFERENCE_ONLY"
    point_in_time_verified: Literal[False] = False
    independent_benchmark_verified: Literal[False] = False
    candidate_promotable: Literal[False] = False


def inspect_development_market_reference(
    dataset: MarketDataSet, *, initial_cash: float = 10_000.0,
) -> DevelopmentMarketReference:
    """Calculate an in-sample RAW price-only comparator, not independent alpha.

    Same dataset, earliest open purchase, full cash funding including costs,
    last close mark-to-market without fictitious final exit. No dividends,
    splits or provider-vintage correction is silently assumed.
    """
    if dataset.zone != DataZone.DEVELOPMENT:
        raise ResearchCatalogError("only development market reference is available")
    if dataset.timeframe != "1d" or dataset.calendar != "us_equities":
        raise ResearchCatalogError("daily US-equity data required")
    if not dataset.bars or len({b.symbol for b in dataset.bars}) != 1:
        raise ResearchCatalogError("single-symbol market reference required")
    if not isfinite(initial_cash) or initial_cash <= 0:
        raise ResearchCatalogError("invalid market reference cash")
    barriers = []
    source = dataset.provenance
    if source is None:
        barriers.append("vendor_provenance_missing")
    else:
        if source.revision_policy != "as_of":
            barriers.append("latest_revision_not_as_of")
        if (
            source.corporate_action_policy != "total_return_adjusted"
            or not source.corporate_action_reference
        ):
            barriers.append("corporate_action_adjustment_unverified")
        if source.universe_policy not in {"point_in_time", "single_symbol"}:
            barriers.append("historical_investable_universe_unverified")
    # Independent authentication is needed in addition to self-declared metadata.
    barriers.extend((
        "publication_availability_times_unverified",
        "independent_vendor_not_authenticated",
        "historical_vintage_not_independently_certified",
    ))
    rate = _REFERENCE_COST.calculate(1.0, side="buy", stress_multiplier=1.0).total
    notional = initial_cash / (1.0 + rate)
    cost = _REFERENCE_COST.calculate(notional, side="buy", stress_multiplier=1.0).total
    cash = initial_cash - notional - cost
    shares = notional / dataset.bars[0].open
    final_equity = cash + shares * dataset.bars[-1].close
    if not isfinite(final_equity) or final_equity <= 0:
        raise ResearchCatalogError("invalid market reference final equity")
    body = {
        "dataset": dataset.dataset_hash,
        "cost": _REFERENCE_COST.version,
        "initial_cash": initial_cash,
        "price_only_final": final_equity,
        "purchase_cost": cost,
        "blockers": barriers,
        "label": "development-same-source-price-only-not-independent-v1",
    }
    return DevelopmentMarketReference(
        dataset_hash=dataset.dataset_hash, reference_hash=content_hash(body),
        symbol=dataset.bars[0].symbol, initial_cash=initial_cash,
        price_only_marked_equity=final_equity, purchase_cost=cost,
        blockers=tuple(barriers),
    )
