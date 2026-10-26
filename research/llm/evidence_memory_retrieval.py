"""M1: deterministic exact-key research memory search (no model/embeddings).

An input handoff digest is an integrity checksum, not a trusted signature. For
live use, source snapshots and S7 must be freshly rechecked by the Quant owner.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from core.integrity.hashes import content_hash


class MemoryRetrievalError(ValueError):
    """An evidence index is invalid, ambiguous, or the query is unsafe."""


_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _validate_handoff(handoff: Mapping[str, Any]) -> list[dict[str, Any]]:
    if (
        handoff.get("schema") != "quant-evidence-memory-handoff-m0-v1"
        or not _valid_hash(handoff.get("handoff_hash"))
        or content_hash({k: v for k, v in handoff.items() if k != "handoff_hash"})
        != handoff["handoff_hash"]
    ):
        raise MemoryRetrievalError("handoff digest or schema invalid")
    events = handoff.get("events")
    if not isinstance(events, list) or len(events) != handoff.get("completed_generations"):
        raise MemoryRetrievalError("handoff generation index invalid")
    prior: str | None = None
    for generation, event in enumerate(events, 1):
        if (
            not isinstance(event, dict)
            or event.get("generation") != generation
            or not _valid_hash(event.get("event_hash"))
            or not _valid_hash(event.get("evidence_hash"))
            or event.get("previous_evidence_hash") != prior
            or content_hash({k: v for k, v in event.items() if k != "event_hash"})
            != event["event_hash"]
        ):
            raise MemoryRetrievalError("event digest or generation chain invalid")
        if not isinstance(event.get("experiments"), list):
            raise MemoryRetrievalError("event experiment index absent")
        prior = event["evidence_hash"]
    if (
        handoff.get("source_evidence_head_hash") != prior
        or handoff.get("orders_enabled") is not False
        or handoff.get("independent_oos_approved") is not False
    ):
        raise MemoryRetrievalError("handoff source head/scope invalid")
    return events


def search_evidence_memory(
    handoff: Mapping[str, Any],
    *,
    parent_hash: str | None = None,
    intervention_hash: str | None = None,
    finding: str | None = None,
    metric: str | None = None,
    generation: int | None = None,
    only_negative: bool = False,
    limit: int = 8,
) -> dict[str, Any]:
    """Return measured S7 evidence with exact typed identity and replay counts.

    This function cannot distinguish a malicious *fully rehashed* fake handoff;
    downstream use requires a fresh Quant canonical source verification.
    """
    if type(limit) is not int or not 1 <= limit <= 20:
        raise MemoryRetrievalError("limit must be 1..20")
    if parent_hash is not None and not _valid_hash(parent_hash):
        raise MemoryRetrievalError("invalid parent hash")
    if intervention_hash is not None and not _valid_hash(intervention_hash):
        raise MemoryRetrievalError("invalid typed intervention hash")
    if generation is not None and (type(generation) is not int or generation < 1):
        raise MemoryRetrievalError("generation must be positive integer")
    for label, val in (("finding", finding), ("metric", metric)):
        if val is not None and (not isinstance(val, str) or not 1 <= len(val) <= 64):
            raise MemoryRetrievalError(f"invalid {label} query")
    events = _validate_handoff(handoff)
    matched = []
    for event in events:
        if generation is not None and event["generation"] != generation:
            continue
        for trial in event["experiments"]:
            if not isinstance(trial, Mapping):
                raise MemoryRetrievalError("untrusted event experiment")
            identity = trial.get("typed_intervention")
            exact = identity.get("exact_fingerprint") if isinstance(identity, Mapping) else None
            if (
                parent_hash is not None
                and trial.get("parent_strategy_hash") != parent_hash
                or intervention_hash is not None
                and exact != intervention_hash
                or finding is not None
                and trial.get("finding") != finding
                or metric is not None
                and trial.get("metric") != metric
                or only_negative
                and trial.get("finding") == "DIRECTION_MATCHED_DEVELOPMENT_ONLY"
            ):
                continue
            matched.append(
                {
                    "generation": event["generation"],
                    "event_hash": event["event_hash"],
                    "canonical_evidence_hash": event["evidence_hash"],
                    "s7_record_hash": event["s7_record_hash"],
                    "parent_strategy_hash": trial.get("parent_strategy_hash"),
                    "intervention_exact_hash": exact,
                    "intervention_family_hash": (
                        identity.get("family_fingerprint")
                        if isinstance(identity, Mapping)
                        else None
                    ),
                    "hypothesis_id": trial.get("hypothesis_id"),
                    "finding": trial.get("finding"),
                    "metric": trial.get("metric"),
                    "measured_delta": trial.get("measured_delta"),
                    "parent_fill_count": trial.get("parent_fill_count"),
                    "child_fill_count": trial.get("child_fill_count"),
                    "child_strategy_hash": trial.get("child_strategy_hash"),
                    "mechanism_is_unverified": True,
                    "untrusted_model_text_not_instruction": True,
                }
            )
    # Same-parent and typed-intervention exact matches are included through
    # filters; no fabricated similarity score or recency-only exclusion.
    matched.sort(key=lambda x: (-x["generation"], x["hypothesis_id"]))
    return {
        "schema": "quant-exact-evidence-retrieval-m1-v1",
        "source_handoff_hash": handoff["handoff_hash"],
        "query": {
            "parent_hash": parent_hash,
            "intervention_hash": intervention_hash,
            "finding": finding,
            "metric": metric,
            "generation": generation,
            "only_negative": only_negative,
        },
        "total_matches": len(matched),
        "results": matched[:limit],
        "more_evidence_requires_lookup": len(matched) > limit,
        "safe_as_complete_memory": len(matched) <= limit,
        "authenticated_source_rechecked": False,
        "not_evidence_of_causality": True,
        "orders_enabled": False,
        "independent_oos_approved": False,
    }


def audit_evidence_grounding(
    handoff: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    receipts: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    """Enumerate independently sourced, atomic field assertions on test data.

    This is not 50 independent market/regime/model-retrieval test scenarios.
    No new provider turn, order, or market source is invoked.
    """
    from application.research_handoff_builder import build_research_handoff

    regenerated = build_research_handoff(
        snapshot, receipts, max_chars=handoff.get("max_brief_chars", 20000)
    )
    if regenerated["handoff_hash"] != handoff.get("handoff_hash"):
        raise MemoryRetrievalError("handoff disagrees with canonical snapshot/S7")
    events = _validate_handoff(handoff)
    checks: list[bool] = []
    for event, source in zip(events, snapshot["history"], strict=True):
        n = event["generation"]
        look = search_evidence_memory(handoff, generation=n, limit=20)
        refs = {entry["hypothesis_id"]: entry for entry in look["results"]}
        core_fields = (
            "generation",
            "evidence_hash",
            "previous_evidence_hash",
            "strategy_hash",
            "effective_signal_hash",
        )
        for field in core_fields:
            checks.append(event[field] == source.get(field))
        checks.append(event["s7_record_hash"] == receipts[n]["record_hash"])
        for key in (
            "cagr",
            "calmar",
            "exposure",
            "max_drawdown",
            "profit_factor",
            "sharpe",
            "sortino",
            "total_return",
            "trade_count",
            "turnover",
            "win_rate",
        ):
            checks.append(event["measured_metrics"][key] == source["metrics"][key])
        offered = {x["hypothesis_id"]: x for x in source["experiments"]}
        for outcome in receipts[n]["report"]["experiments"]:
            hid = outcome["hypothesis_id"]
            if hid not in refs:
                checks.append(False)
                continue
            selected = refs[hid]
            checks.extend(
                (
                    selected["canonical_evidence_hash"] == source["evidence_hash"],
                    selected["s7_record_hash"] == receipts[n]["record_hash"],
                    selected["hypothesis_id"] == hid,
                    selected["finding"] == outcome["status"],
                    selected["metric"] == outcome["metric"],
                    selected["measured_delta"] == outcome.get("delta"),
                    selected["parent_fill_count"] == outcome["parent_fill_count"],
                    selected["child_fill_count"] == outcome["child_fill_count"],
                    selected["child_strategy_hash"] == outcome["child_strategy_hash"],
                    selected["parent_strategy_hash"] == source["strategy_hash"],
                    offered[hid]["hypothesis_id"] == selected["hypothesis_id"],
                    selected["mechanism_is_unverified"] is True,
                )
            )
    return {
        "schema": "quant-atomic-grounding-qa-m1-v1",
        "questions": len(checks),
        "passed": sum(checks),
        "failed": len(checks) - sum(checks),
        "distinct_fixture_generations": len(events),
        "important_limit": "field_assertions_not_independent_market_or_llm_cases",
        "real_gpt_calls": 0,
        "data_scope": "ISOLATED_NON_PIT_DEVELOPMENT",
    }
