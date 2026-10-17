"""S2 optional fail-closed canonical fill-identity preflight before staging.

StrategyIR hashes and diagnostic gates can differ while the executed orders
remain identical; such changes waste a counted research generation. This
checks exact next-open executed fills AND the resulting costed equity curve.
Does not establish causality, profit, or independent OOS generalization.
"""

from __future__ import annotations

from dataclasses import asdict

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.decision_audit import AcademicDecisionAudit
from research.indicator_engine.strategy_adapter import (
    CompiledAcademicStrategy,
    evaluate_compiled_development,
)


class UnchangedCanonicalExecution(ValueError):
    """Mutated StrategyIR reproduces the same costed fills as its parent."""


def compare_inherited_s2_execution(
    parent: CompiledAcademicStrategy,
    child: AcademicDecisionAudit,
    market: MarketDataSet,
) -> dict[str, object]:
    if market.zone != DataZone.DEVELOPMENT:
        raise ValueError("S2 execution preflight only supports development data")
    if (
        parent.strategy_hash == child.evaluation.strategy_hash
        or parent.dataset_hash != market.dataset_hash
        or child.evaluation.dataset_hash != market.dataset_hash
        or parent.broker_executable is not False
        or child.broker_executable is not False
    ):
        raise ValueError("S2 execution preflight parent/child source identity mismatch")
    parent_eval = evaluate_compiled_development(parent, market)
    child_eval = child.evaluation
    # Use *actual* canonical fills with quantities, prices, timestamps, costs;
    # never compare strategy-prefixed audit fill IDs or signal-only proxies.
    unchanged = parent_eval.trades == child_eval.trades
    same_curve = parent_eval.equity_curve == child_eval.equity_curve
    if unchanged != same_curve:
        raise ValueError("S2 execution preflight inconsistent canonical fills/equity")
    if unchanged:
        raise UnchangedCanonicalExecution(
            "UNCHANGED_CANONICAL_FILLS: candidate has the same real executed "
            "orders and costed equity as the selected parent. No generation "
            "was consumed; revise the plan using the same checkpoint token"
        )
    # Bounded metadata: SHA of full trace, counts, not giant data arrays.
    return {
        "schema": "t4-s2-canonical-execution-preflight-v1",
        "status": "VERIFIED_DIFFERENT_COSTED_FILLS",
        "parent_strategy_hash": parent.strategy_hash,
        "candidate_strategy_hash": child_eval.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "parent_canonical_fills_hash": content_hash([asdict(x) for x in parent_eval.trades]),
        "candidate_canonical_fills_hash": content_hash([asdict(x) for x in child_eval.trades]),
        "parent_fill_count": parent_eval.trades_count,
        "candidate_fill_count": child_eval.trades_count,
        "same_fill_trace": False,
        "costed_equity_changed": True,
        "comparison_is_development_only": True,
        "causal_status": "NOT_ESTABLISHED",
        "independent_oos_approved": False,
        "broker_executable": False,
    }
