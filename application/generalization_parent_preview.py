"""Offline-only bridge: audited counted-generation replays -> ex-post parent review.

MUST operate on a separate isolated read-only-origin SQLite snapshot, not the
live AcademicMCPCheckpointService. It never persists a pinned parent, advances
a generation, or confers any OOS / broker permission. COUNTED_S7_CHILD requires
a separate signed child audit binding and is intentionally not admitted here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.data.contracts import DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.inherited_historical_robustness import (
    evaluate_inherited_historical_robustness,
)
from research.llm.generalization_parent_v1 import (
    GeneralizationParentChoice,
    select_generalization_parent,
)


def preview_counted_parent_generalization(
    service: AcademicMCPCheckpointService,
    catalog: ResearchCatalog,
    market: MarketDataSet,
    *,
    session_id: str,
    generations: Sequence[int],
    years: Sequence[int],
    last_development_date: date,
    next_generation: int,
) -> GeneralizationParentChoice:
    """Audit and compare only explicit counted parents in an ISOLATED service.

    The caller is responsible for populating service.state from copied
    SQLite backups, so this code cannot independently verify vendor authenticity.
    Selection is diagnostic and explicitly not a replacement for the existing
    persisted AcademicMCPCheckpointService parent-selection path.
    """
    if (
        market.zone != DataZone.DEVELOPMENT
        or not market.bars
        or any(x.symbol != "QQQ" for x in market.bars)
        or not generations
        or len(generations) > 8
        or any(type(n) is not int for n in generations)
        or len(set(generations)) != len(generations)
    ):
        raise ResearchCatalogError("invalid offline counted-parent preview scope")
    if service.state.resolve().is_relative_to(service.root.resolve()):
        raise ResearchCatalogError("parent preview requires external isolated state snapshot")
    if market.bars[-1].timestamp.date() > last_development_date:
        raise ResearchCatalogError("parent preview outside development cutoff")
    state = service.cycle.get(session_id, catalog, market)
    source = state["history"]
    if any(n < 1 or n > len(source) for n in generations):
        raise ResearchCatalogError("parent preview contains uncounted generation")
    candidates = []
    reports = {}
    for generation in generations:
        evidence = source[generation - 1]
        if evidence.get("inherited_strategy_ir") is None:
            raise ResearchCatalogError("counted parent lacks inherited StrategyIR")
        compiled = service._inherited_from_evidence(
            catalog, market, evidence, history=source, session_id=session_id,
        )
        review = evaluate_inherited_historical_robustness(
            compiled, evidence, market, years=years,
            last_development_date=last_development_date,
        )
        reports[compiled.strategy_hash] = review
        metrics = evidence["metrics"]
        candidates.append({
            "source_generation": generation,
            "source_kind": "COUNTED_GENERATION",
            "source_evidence_hash": evidence["evidence_hash"],
            "audit_hash": evidence["audit_hash"],
            "effective_signal_hash": evidence["effective_signal_hash"],
            "successor_strategy_hash": compiled.strategy_hash,
            "replay_verified": True,
            "independent_oos_approved": False,
            "broker_executable": False,
            "parent_quality": {
                "total_return": metrics["total_return"],
                "max_drawdown": metrics["max_drawdown"],
                "closed_trades": metrics["trade_count"],
                "market_exposure": metrics["exposure"],
            },
        })
    return select_generalization_parent(
        candidates, reports, next_generation=next_generation,
    )
