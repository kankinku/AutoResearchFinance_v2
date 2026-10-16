"""Reconstruct S7 children, then evolve the EXACT child StrategyIR, never a proxy.

This is a chained development-only comparison. No automatic generation
increment, no executable approval, and no PIT/OOS claims.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from math import isclose
from typing import Any

from core.data.contracts import DataZone, MarketDataSet
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from evaluation.metrics import calculate_metrics
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    compile_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.controlled_experiments import _execution_delta
from research.indicator_engine.strategy_adapter import evaluate_compiled_development
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent


class LineageReplayError(ValueError):
    """Untrusted research child or unsupported successor mutation."""


def _single(items: list[dict[str, Any]], field: str, match: str) -> dict[str, Any]:
    found = [item for item in items if item.get(field) == match]
    if len(found) != 1:
        raise LineageReplayError("source child hypothesis missing or duplicated")
    return found[0]


def _close(a: Any, b: Any) -> bool:
    return (
        type(a) in (int, float)
        and type(b) in (int, float)
        and isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-6)
    )


def verified_child_successor(
    catalog: ResearchCatalog,
    market: MarketDataSet,
    original: dict[str, Any],
    stored_report: dict[str, Any],
    *,
    hypothesis_id: str,
    expected_child_strategy_hash: str,
    continuation_intent: dict[str, Any],
) -> dict[str, Any]:
    """Verify immutable evidence and matched economics BEFORE applying child->grandchild.

    Caller must fetch original from the cycle's hash-checked history and report
    through the gateway's verified record loader; verify both identities again.
    """
    if (
        market.zone != DataZone.DEVELOPMENT
        or original.get("dataset_hash") != market.dataset_hash
        or stored_report.get("original_generation_evidence_hash") != original.get("evidence_hash")
        or stored_report.get("report", {}).get("dataset_hash") != market.dataset_hash
        or stored_report.get("report", {}).get("diagnostic_proposal_hash")
        != original.get("diagnostic_proposal_hash")
        or stored_report.get("study_scope") != "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF"
    ):
        raise LineageReplayError("source development evidence identity mismatch")
    digest = stored_report.get("record_hash")
    if (
        not isinstance(digest, str)
        or content_hash({k: v for k, v in stored_report.items() if k != "record_hash"}) != digest
    ):
        raise LineageReplayError("source experiment record integrity mismatch")
    report = stored_report["report"]
    if (
        report.get("out_of_sample_approved") is not False
        or report.get("broker_executable") is not False
        or report.get("causal_status") != "NOT_ESTABLISHED"
    ):
        raise LineageReplayError("unapproved development result cannot be inherited")

    plan = AlgorithmPlan.model_validate(original["algorithm_plan"])
    compiled = compile_algorithm_plan(catalog, plan, market)
    if (
        compiled.plan_hash != original.get("plan_hash")
        or compiled.compiled.strategy_hash != original.get("strategy_hash")
        or report.get("plan_hash") != original.get("plan_hash")
        or report.get("audit_hash") != original.get("audit_hash")
    ):
        raise LineageReplayError("original plan and audit identity mismatch")
    audit = audit_algorithm_plan(catalog, compiled, market)
    if audit.trace_hash != original.get("audit_hash") or not _close(
        audit.evaluation.final_equity, original.get("measured_final_equity")
    ):
        raise LineageReplayError("original generation cannot be replayed")

    proposal = _single(original["experiments"], "hypothesis_id", hypothesis_id)
    measured = _single(report["experiments"], "hypothesis_id", hypothesis_id)
    if (
        measured.get("causal_status") != "NOT_ESTABLISHED"
        or measured.get("child_strategy_hash") != proposal.get("proposal_child_hash")
        or measured.get("child_strategy_hash") != expected_child_strategy_hash
        or not _close(measured.get("parent_final_equity"), audit.evaluation.final_equity)
    ):
        raise LineageReplayError("child identity, parent economics or hypothesis mismatch")

    first = ResearchIntent.model_validate(proposal["proposed_intent"])
    if first.parent_ids != (compiled.compiled.strategy.strategy_id,):
        raise LineageReplayError("original mutation parent was changed")
    child_ir = apply_intent(compiled.compiled.strategy, first, research_feature_specs())
    hash_child = content_hash(child_ir.model_dump(mode="json", by_alias=True))
    if hash_child != expected_child_strategy_hash:
        raise LineageReplayError("reconstructed child StrategyIR hash mismatch")
    child = evaluate_compiled_development(
        replace(compiled.compiled, strategy=child_ir, strategy_hash=hash_child),
        market,
    )
    if (
        not _close(child.final_equity, measured.get("child_final_equity"))
        or child.trades_count != measured.get("child_fill_count")
        or not _close(child.total_paid_costs, measured["execution_delta"]["child_costs"])
    ):
        raise LineageReplayError("replayed child fills, final capital or fees differ")
    if sum(trade.side == "sell" for trade in child.trades) < 30:
        raise LineageReplayError("inherited child has fewer than 30 closed trade pairs")
    if child.final_equity <= audit.evaluation.final_equity:
        raise LineageReplayError("inherited child failed economic improvement requirement")

    continuation = ResearchIntent.model_validate(continuation_intent)
    if (
        continuation.mode != "structure"
        or continuation.parent_ids != (child_ir.strategy_id,)
        or continuation.feature_proposal is not None
        or continuation.primitive_request is not None
        or not 1 <= len(continuation.operations) <= 6
    ):
        raise LineageReplayError("continuation must be a bounded registered child mutation")
    successor_ir = apply_intent(child_ir, continuation, research_feature_specs())
    successor_hash = content_hash(successor_ir.model_dump(mode="json", by_alias=True))
    if successor_hash == hash_child:
        raise LineageReplayError("successor mutation did not modify child")
    successor = evaluate_compiled_development(
        replace(compiled.compiled, strategy=successor_ir, strategy_hash=successor_hash),
        market,
    )
    delta = _execution_delta(child, successor)
    if not (delta.execution_timing_changed or delta.resized_event_count):
        raise LineageReplayError("successor has no observed fill timing/quantity change")
    parent_metrics = calculate_metrics(child.equity_curve, (), periods_per_year=252)
    successor_metrics = calculate_metrics(successor.equity_curve, (), periods_per_year=252)
    body = {
        "schema": "p0-3-child-to-successor-development-v1",
        "source_generation": original["generation"],
        "hypothesis_id": hypothesis_id,
        "source_evidence_hash": original["evidence_hash"],
        "source_experiment_report_hash": digest,
        "dataset_hash": market.dataset_hash,
        "original_strategy_hash": original["strategy_hash"],
        "reproduced_child_strategy_hash": hash_child,
        "child_equity_hash": child.equity_hash,
        "child_final_equity": child.final_equity,
        "child_total_return": parent_metrics.total_return,
        "child_max_drawdown": parent_metrics.max_drawdown,
        "child_fills": child.trades_count,
        "child_costs": child.total_paid_costs,
        "successor_strategy_hash": successor_hash,
        "successor_equity_hash": successor.equity_hash,
        "successor_final_equity": successor.final_equity,
        "successor_total_return": successor_metrics.total_return,
        "successor_max_drawdown": successor_metrics.max_drawdown,
        "successor_fills": successor.trades_count,
        "successor_costs": successor.total_paid_costs,
        "improvement_vs_child_pp": 100
        * (successor_metrics.total_return - parent_metrics.total_return),
        "execution_delta": asdict(delta),
        "continuation_intent": continuation.model_dump(mode="json"),
        "continuation_intent_hash": content_hash(continuation.model_dump(mode="json")),
        "algorithm_parent": "REPLAYED_S7_CHILD_STRATEGY_IR",
        "generation_counter_incremented": False,
        "scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        "causal_status": "NOT_ESTABLISHED",
        "independent_oos_approved": False,
        "broker_executable": False,
        "approval": "RESEARCH_REPLAY_ONLY_NOT_PROMOTED",
    }
    return {**body, "report_hash": content_hash(body)}
