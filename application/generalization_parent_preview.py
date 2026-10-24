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


def preview_mixed_parent_generalization(
    service: AcademicMCPCheckpointService,
    catalog: ResearchCatalog,
    market: MarketDataSet,
    *,
    session_id: str,
    sources: Sequence[tuple[int, str | None]],
    years: Sequence[int],
    last_development_date: date,
    next_generation: int,
) -> GeneralizationParentChoice:
    """Replay counted parents AND authenticated S7 children in an isolated clone.

    Sources are (counted_generation, optional S7 hypothesis_id). The exact
    counted-parent and S7 lineage proofs are checked by the EXISTING canonical
    services first, and the child's full independent decision audit binds its
    actual StrategyIR, indicator vectors, every fill and cost. Parent election
    is research-only; no state or parent table is modified by this function.
    """
    from core.backtest.engine import _regime_allows, _rules_match
    from core.integrity.hashes import content_hash
    from research.indicator_engine.algorithm_plan import (
        AlgorithmPlan,
        audit_algorithm_plan,
        compile_algorithm_plan,
    )
    from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
    from research.llm.lineage_selection import replay_counted_s7_child

    if (
        market.zone != DataZone.DEVELOPMENT
        or not market.bars
        or any(bar.symbol != "QQQ" for bar in market.bars)
        or not sources
        or len(sources) > 8
        or len(set(sources)) != len(sources)
        or any(
            type(g) is not int
            or (h is not None and (not isinstance(h, str) or not h))
            for g, h in sources
        )
    ):
        raise ResearchCatalogError("invalid mixed generalization preview source")
    if service.state.resolve().is_relative_to(service.root.resolve()):
        raise ResearchCatalogError("mixed parent preview requires external isolated state")
    if market.bars[-1].timestamp.date() > last_development_date:
        raise ResearchCatalogError("mixed preview beyond development cutoff")
    state = service.cycle.get(session_id, catalog, market)
    history = state["history"]
    if any(g < 1 or g > len(history) for g, _ in sources):
        raise ResearchCatalogError("mixed preview references future counted generation")

    candidates = []
    reports = {}
    for generation, hypothesis_id in sources:
        evidence = history[generation - 1]
        if evidence.get("inherited_strategy_ir") is not None:
            parent = service._inherited_from_evidence(
                catalog, market, evidence, history=history, session_id=session_id,
            )
            audited_parent = audit_inherited_decisions(parent, market)
        else:
            planned = compile_algorithm_plan(
                catalog, AlgorithmPlan.model_validate(evidence["algorithm_plan"]), market,
            )
            audited_parent = audit_algorithm_plan(catalog, planned, market)
            parent = planned.compiled
            if (
                parent.strategy_hash != evidence["strategy_hash"]
                or planned.plan_hash != evidence["plan_hash"]
                or audited_parent.trace_hash != evidence["audit_hash"]
                or abs(
                    audited_parent.evaluation.final_equity
                    - evidence["measured_final_equity"]
                ) > 1e-6
            ):
                raise ResearchCatalogError("uncounted source AlgorithmPlan audit mismatch")

        if hypothesis_id is None:
            if evidence.get("inherited_strategy_ir") is None:
                raise ResearchCatalogError("non-inherited counted parent unsupported")
            compiled = parent
            child_evidence = evidence
            candidate = {
                "source_generation": generation,
                "source_kind": "COUNTED_GENERATION",
                "source_evidence_hash": evidence["evidence_hash"],
                "audit_hash": evidence["audit_hash"],
                "effective_signal_hash": evidence["effective_signal_hash"],
                "successor_strategy_hash": parent.strategy_hash,
                "replay_verified": True,
                "independent_oos_approved": False,
                "broker_executable": False,
                "parent_quality": {
                    "total_return": evidence["metrics"]["total_return"],
                    "max_drawdown": evidence["metrics"]["max_drawdown"],
                    "closed_trades": evidence["metrics"]["trade_count"],
                    "market_exposure": evidence["metrics"]["exposure"],
                },
            }
        else:
            with service._connect() as db:
                s7 = service._stored_experiment(db, session_id, generation)
            if s7 is None:
                raise ResearchCatalogError("S7 parent report missing")
            signed, compiled = replay_counted_s7_child(
                catalog, market, evidence, s7, parent, hypothesis_id,
            )
            audited_child = audit_inherited_decisions(compiled, market)
            # The proof is strictly derived from validated original S7 source,
            # not a newly claimed independent generation or OOS result.
            child_evidence = {
                "generation": generation,
                "strategy_hash": compiled.strategy_hash,
                "dataset_hash": market.dataset_hash,
                "audit_hash": audited_child.trace_hash,
                "measured_final_equity": audited_child.evaluation.final_equity,
                "metrics": {"trade_count": len(audited_child.round_trips)},
                "evidence_hash": evidence["evidence_hash"],
                "broker_executable": False,
                "independent_oos_approved": False,
            }
            signal_values = {
                name: list(series) for name, series in compiled.feature_values.items()
            }
            signal_fingerprint = content_hash({
                "dataset_hash": market.dataset_hash,
                "entry": tuple(
                    _rules_match(
                        compiled.strategy.entry.conditions,
                        compiled.strategy.entry.logic,
                        signal_values, i,
                    )
                    for i in range(len(market.bars))
                ),
                "exit": tuple(
                    _rules_match(
                        compiled.strategy.exit.conditions,
                        compiled.strategy.exit.logic,
                        signal_values, i,
                    )
                    for i in range(len(market.bars))
                ),
                "regime": tuple(
                    _regime_allows(compiled.strategy, signal_values, i)
                    for i in range(len(market.bars))
                ),
            })
            candidate = {
                **signed,
                "audit_hash": audited_child.trace_hash,
                "effective_signal_hash": signal_fingerprint,
                "parent_quality": {
                    "total_return": signed["successor_total_return"],
                    "max_drawdown": signed["successor_max_drawdown"],
                    "closed_trades": signed["successor_closed_trades"],
                    "market_exposure": signed["successor_market_exposure"],
                },
            }
        report = evaluate_inherited_historical_robustness(
            compiled, child_evidence, market, years=years,
            last_development_date=last_development_date,
        )
        if compiled.strategy_hash in reports:
            raise ResearchCatalogError("duplicate inherited candidate strategy")
        candidates.append(candidate)
        reports[compiled.strategy_hash] = report
    return select_generalization_parent(
        candidates, reports, next_generation=next_generation,
    )
