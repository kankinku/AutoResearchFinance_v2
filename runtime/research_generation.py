"""Pure generation context/report assembly, separated from retries and worker lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mutation.engine import MutationOperation
from orchestration.evaluation_runner import build_research_context
from research.llm.codex_exec import sanitize_context
from research.llm.director import ResearchIntent
from strategy_ir.schema import StrategyIR


def build_generation_context(
    state_dir: Path, source_path: Path | None, current: StrategyIR
) -> dict[str, Any]:
    """Retain historic eligible frontier rather than erasing it each generation."""
    context = build_research_context(state_dir, source_path=source_path)
    frontier_raw = context.get("frontier", [])
    frontier = list(frontier_raw) if isinstance(frontier_raw, list) else []
    if not any(
        isinstance(item, dict)
        and (
            item.get("candidate_hash") == current.strategy_id
            or item.get("id") == current.strategy_id
        )
        for item in frontier
    ):
        frontier.append({"id": current.strategy_id, "family": current.family})
    context.update(
        {
            "generation": current.generation,
            "source_strategy": current.model_dump(mode="json", by_alias=True),
            "parent_ids_hint": [current.strategy_id],
            "frontier": frontier,
        }
    )
    return context


def _intent_payload(intent: ResearchIntent | None) -> dict[str, object] | None:
    if intent is None:
        return None
    sanitized = sanitize_context(intent.model_dump(mode="json", exclude_none=True))
    return sanitized if isinstance(sanitized, dict) else None


def build_generation_record(
    *,
    generation: int,
    parent_id: str,
    intent: ResearchIntent | None,
    intent_status: str,
    operations: Sequence[MutationOperation],
    evaluation: Mapping[str, object] | None,
    intent_error: str | None,
    evaluation_error: str | None,
    repair_attempts: int,
    repair_errors: Sequence[str],
    repair_history: Sequence[dict[str, object]],
    research_run_id: str,
) -> dict[str, object]:
    """Deterministic, sanitized success/fallback/degraded generation summary."""
    if evaluation is not None:
        status = (
            intent_status
            if intent_status != "PROPOSED"
            else str(evaluation.get("status", "UNKNOWN"))
        )
        record: dict[str, object] = {
            "generation": generation,
            "parent_id": parent_id,
            "status": status,
            "intent_status": intent_status,
            "intent": _intent_payload(intent),
            "operations": [{"op": op.op, "path": op.path} for op in operations],
            "evaluation": sanitize_context(dict(evaluation)),
        }
    else:
        record = {
            "generation": generation,
            "parent_id": parent_id,
            "status": "DEGRADED",
            "intent_status": intent_status,
            "intent": _intent_payload(intent),
            "operations": [],
        }
    if intent_error is not None:
        record["intent_error"] = intent_error
    if repair_attempts:
        record["repair_attempts"] = repair_attempts
        record["repair_errors"] = list(repair_errors)
        record["repair_history"] = list(repair_history)
    if evaluation_error is not None:
        record["evaluation_error"] = evaluation_error
    record["research_run_id"] = research_run_id
    return record
