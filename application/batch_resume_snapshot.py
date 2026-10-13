"""Typed, integrity-checked continuation state for deterministic GPT batch workers.

A checkpoint is never evidence of evaluation by itself. It is usable only
alongside matching immutable run/generation/attempt Evidence and SQLite history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.research_hypothesis import LocalHypothesis
from memory.evidence_store import EvidenceIntegrityError, digest
from mutation.engine import MutationOperation
from mutation.parameter import ParameterDomain
from strategy_ir.schema import StrategyIR
from strategy_ir.validator import validate_strategy


@dataclass(frozen=True)
class BatchContinuation:
    strategy: StrategyIR
    seen_semantics: frozenset[str]
    used_hypotheses: frozenset[str]
    next_hypothesis: LocalHypothesis | None
    input_sha256: dict[str, str]
    generation_event_checksum: str


def _operation(op: MutationOperation) -> dict[str, Any]:
    return {
        "op": op.op,
        "path": op.path,
        "value": op.value,
        "other": op.other.model_dump(mode="json") if op.other is not None else None,
    }


def _decode_operation(raw: dict[str, Any]) -> MutationOperation:
    other = raw.get("other")
    return MutationOperation(
        op=raw["op"],
        path=raw.get("path"),
        value=raw.get("value"),
        other=validate_strategy(StrategyIR.model_validate(other)) if other is not None else None,
    )


def encode_checkpoint(snapshot: BatchContinuation) -> dict[str, Any]:
    next_plan: dict[str, Any] | None = None
    if snapshot.next_hypothesis is not None:
        plan = snapshot.next_hypothesis
        next_plan = {
            "reason_code": plan.reason_code,
            "trigger_gate": plan.trigger_gate,
            "applied_after_attempt_id": plan.applied_after_attempt_id,
            "operations": [_operation(op) for op in plan.operations],
            "domains": [{"name": d.name, "values": list(d.values)} for d in plan.domains],
            "preview_new_candidates": plan.preview_new_candidates,
            "rescue_candidate_hash": plan.rescue_candidate_hash,
        }
    return {
        "version": 1,
        "strategy": snapshot.strategy.model_dump(mode="json"),
        "seen_semantics": sorted(snapshot.seen_semantics),
        "used_hypotheses": sorted(snapshot.used_hypotheses),
        "next_hypothesis": next_plan,
        "input_sha256": snapshot.input_sha256,
        "generation_event_checksum": snapshot.generation_event_checksum,
    }


def decode_checkpoint(payload: dict[str, Any], checksum: str) -> BatchContinuation:
    if digest(payload) != checksum or payload.get("version") != 1:
        raise EvidenceIntegrityError("research continuation checkpoint hash invalid")
    try:
        next_plan = payload.get("next_hypothesis")
        hypothesis = None
        if next_plan is not None:
            hypothesis = LocalHypothesis(
                reason_code=next_plan["reason_code"],
                trigger_gate=next_plan["trigger_gate"],
                applied_after_attempt_id=next_plan["applied_after_attempt_id"],
                operations=tuple(_decode_operation(op) for op in next_plan["operations"]),
                domains=tuple(
                    ParameterDomain(d["name"], tuple(d["values"])) for d in next_plan["domains"]
                ),
                preview_new_candidates=next_plan["preview_new_candidates"],
                rescue_candidate_hash=next_plan.get("rescue_candidate_hash"),
            )
        strategy = validate_strategy(StrategyIR.model_validate(payload["strategy"]))
        seen = payload["seen_semantics"]
        used = payload["used_hypotheses"]
        input_hashes = payload["input_sha256"]
        recorded_checksum = payload["generation_event_checksum"]
        if (
            not isinstance(seen, list)
            or not isinstance(used, list)
            or not all(isinstance(s, str) and len(s) == 64 for s in seen)
            or len(seen) != len(set(seen))
            or not all(isinstance(s, str) for s in used)
            or len(used) != len(set(used))
            or not isinstance(input_hashes, dict)
            or not input_hashes
            or any(
                not isinstance(k, str) or not isinstance(v, str) or len(v) != 64
                for k, v in input_hashes.items()
            )
            or not isinstance(recorded_checksum, str)
            or len(recorded_checksum) != 64
        ):
            raise ValueError("incomplete continuation fields")
        return BatchContinuation(
            strategy,
            frozenset(seen),
            frozenset(used),
            hypothesis,
            input_hashes,
            recorded_checksum,
        )
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise EvidenceIntegrityError("research continuation payload malformed") from exc
