"""Evidence-backed parent donor checkout for V3, RESEARCH-ONLY.

The caller must supply a physically isolated clone of the academic checkpoint
database. This adapter delegates 100% lineage replay to the existing audited
AcademicMCPCheckpointService, then binds each source to its S7 report hash.
No gateway original is modified and no broker/OOS action is reachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from core.data.contracts import DataZone, MarketDataSet
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy
from research.llm.composite_crossover_v3 import VerifiedDonor

if TYPE_CHECKING:
    from application.academic_checkpoint_service import AcademicMCPCheckpointService


class LedgerDonorError(ValueError):
    """Source generation, saved S7 or exact fill replay could not be verified."""


@dataclass(frozen=True)
class LedgerDonorCheckout:
    market: MarketDataSet
    donors: tuple[VerifiedDonor, ...]
    compiled_by_hash: dict[str, CompiledAcademicStrategy]
    original_session_head_hash: str
    dev_only: bool = True
    broker_executable: bool = False
    independent_oos_approved: bool = False


def checkout_counted_donors(
    service: AcademicMCPCheckpointService,
    session_id: str,
    generations: tuple[int, ...],
) -> LedgerDonorCheckout:
    """Verify complete count chain, each saved S7, StrategyIR and costed S2.

    Unlike a client supplied replay_verified=True flag, this receipt can only
    be constructed after an actual saved-checkpoint audit for every requested
    generation. Only eligible *counted* parent strategies are supported here.
    Counted S7 successor donors require a separately implemented checkout.
    """
    if (
        not generations
        or len(generations) != len(set(generations))
        or any(type(g) is not int or g < 1 for g in generations)
        or not isinstance(session_id, str)
        or len(session_id) != 32
    ):
        raise LedgerDonorError("invalid pinned source generations/session")
    with service._connect() as db:
        _, catalog, market, status = service._state(db, session_id)
        if market.zone != DataZone.DEVELOPMENT:
            raise LedgerDonorError("counted parents require development-only market")
        if (
            not status["history"]
            or status["session_id"] != session_id
            or max(generations) > status["completed_generations"]
        ):
            raise LedgerDonorError("counted parent source generation unavailable")
        verified: list[VerifiedDonor] = []
        compiled: dict[str, CompiledAcademicStrategy] = {}
        for g in generations:
            evidence = status["history"][g - 1]
            if evidence["generation"] != g or evidence.get("inherited_strategy_ir") is None:
                raise LedgerDonorError("counted generation has no recorded StrategyIR")
            report = service._stored_experiment(db, session_id, g)
            if (
                report is None
                or report.get("original_generation_evidence_hash") != evidence["evidence_hash"]
                or report.get("study_scope") != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
            ):
                raise LedgerDonorError("counted S7 report missing/mismatched")
            parent = service._inherited_from_evidence(catalog, market, evidence)
            audit = audit_inherited_decisions(parent, market)
            measures = evidence["metrics"]
            observed = cast(dict[str, Any], audit.llm_packet["metrics"])
            if (
                abs(observed["total_return"] - measures["total_return"]) > 1e-9
                or abs(observed["max_drawdown"] - measures["max_drawdown"]) > 1e-9
                or len(audit.round_trips) != measures["trade_count"]
            ):
                raise LedgerDonorError("counted metrics diverged from replay")
            item = VerifiedDonor(
                generation=g,
                evidence_hash=evidence["evidence_hash"],
                report_hash=report["record_hash"],
                strategy=parent.strategy,
                strategy_hash=parent.strategy_hash,
                replay_verified=True,
            )
            if item.strategy_hash in compiled:
                raise LedgerDonorError("distinct source generations share one effective IR")
            verified.append(item)
            compiled[parent.strategy_hash] = parent
        return LedgerDonorCheckout(
            market=market,
            donors=tuple(verified),
            compiled_by_hash=compiled,
            original_session_head_hash=status["history"][-1]["evidence_hash"],
        )
