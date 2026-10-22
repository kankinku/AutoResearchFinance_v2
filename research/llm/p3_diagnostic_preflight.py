"""P3 opt-in: inspect typed, audit-bound S7 next_intent proposals before counting.

Reject only conservative scalar implications or identical sampled development
signals with unchanged risk. This is not predictive alpha or OOS validation.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy
from research.llm.diagnostic_research import (
    approve_diagnostic_plan,
    build_diagnostic_context,
)
from research.llm.p3_semantic_preflight import inspect_inherited_semantics


def inspect_diagnostic_next_intents(
    compiled: CompiledAcademicStrategy,
    data: MarketDataSet,
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    """Validate diagnosis against S2 audit, then preflight each resulting child."""
    audit = audit_inherited_decisions(compiled, data)
    context = build_diagnostic_context(audit, compiled.strategy)
    verified = approve_diagnostic_plan(audit, compiled.strategy, context, diagnosis)
    rejected = []
    inspected = []
    for candidate in verified.experiments:
        child = replace(
            compiled,
            strategy=candidate.child,
            strategy_hash=candidate.child_hash,
        )
        finding = inspect_inherited_semantics(
            compiled, child, bars=len(data.bars), dataset_hash=data.dataset_hash,
        )
        inspected.append({
            "hypothesis_id": candidate.hypothesis_id,
            "review": finding,
        })
        if finding["reject"]:
            rejected.append(candidate.hypothesis_id)
    body = {
        "schema": "p3-diagnostic-next-intent-preflight-v1",
        "dataset_hash": data.dataset_hash,
        "strategy_hash": compiled.strategy_hash,
        "audit_hash": audit.trace_hash,
        "diagnosis_hash": content_hash(diagnosis),
        "reviews": inspected,
        "rejected_hypothesis_ids": rejected,
        "reject": bool(rejected),
        "scope": "REUSED_DEVELOPMENT_NO_OOS_OR_CAUSAL_CLAIM",
    }
    return {**body, "review_hash": content_hash(body)}
