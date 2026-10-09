"""Generation preparation and reporting contracts are independent of retry orchestration."""

from __future__ import annotations

from pathlib import Path

from memory.evidence_store import EvidenceStore
from runtime.research_generation import build_generation_context, build_generation_record
from strategy_ir.validator import validate_strategy
from tests.strategy_ir.test_schema import example_document


def _source() -> object:
    return validate_strategy(example_document())


def test_generation_context_preserves_evidence_frontier_and_current_parent(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.append(
        "run",
        "run:one",
        {
            "research_run_id": "one",
            "requested_generations": 1,
            "seed": 0,
        },
    )
    store.append(
        "attempt",
        "attempt:old",
        {
            "research_run_id": "one",
            "attempt_id": "old",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "historical-winner",
                    "family": "trend",
                    "score": 0.9,
                    "status": "SURVIVOR",
                    "failed_gates": [],
                },
            ],
        },
    )
    context = build_generation_context(tmp_path, None, _source())
    assert any(item.get("candidate_hash") == "historical-winner" for item in context["frontier"])
    assert any(item.get("id") == _source().strategy_id for item in context["frontier"])
    assert context["parent_ids_hint"] == [_source().strategy_id]
    assert "sealed_oos" not in str(context)


def test_generation_context_without_evidence_retains_parent_hint(tmp_path: Path) -> None:
    context = build_generation_context(tmp_path, None, _source())
    assert context["frontier"] == [{"id": _source().strategy_id, "family": _source().family}]


def test_generation_record_preserves_fallback_and_degraded_semantics() -> None:
    fallback = build_generation_record(
        generation=2,
        parent_id="parent-1",
        intent=None,
        intent_status="FALLBACK",
        operations=(),
        evaluation={"status": "COMPLETED", "candidate_count": 2},
        intent_error="invalid",
        evaluation_error=None,
        repair_attempts=1,
        repair_errors=["bad"],
        repair_history=[{"attempt": 1, "status": "FAILED"}],
        research_run_id="research-1",
    )
    assert fallback["status"] == "FALLBACK"
    assert fallback["repair_attempts"] == 1
    assert fallback["evaluation"]["candidate_count"] == 2
    degraded = build_generation_record(
        generation=2,
        parent_id="parent-1",
        intent=None,
        intent_status="FALLBACK",
        operations=(),
        evaluation=None,
        intent_error=None,
        evaluation_error="crashed",
        repair_attempts=0,
        repair_errors=[],
        repair_history=[],
        research_run_id="research-1",
    )
    assert degraded["status"] == "DEGRADED"
    assert degraded["operations"] == []
    assert degraded["evaluation_error"] == "crashed"
