"""Generation preparation and reporting contracts are independent of retry orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

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


def test_requested_frontier_parent_requires_same_research_run(tmp_path: Path) -> None:
    from core.integrity.hashes import content_hash
    from research.llm.director import ResearchIntent
    from runtime.research_generation import select_intent_parent

    source = _source()
    # A distinct, valid canonical parent with a different Strategy IR id.
    alternative = source.model_copy(update={"strategy_id": "different-parent"})
    assert alternative.strategy_id != source.strategy_id
    snapshot = alternative.model_dump(mode="json", by_alias=True)
    store = EvidenceStore(tmp_path)
    store.append(
        "run", "run:old", {"research_run_id": "old", "requested_generations": 1, "seed": 1}
    )
    store.append(
        "attempt",
        "attempt:old",
        {
            "research_run_id": "old",
            "attempt_id": "old",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "f1",
                    "family": "trend",
                    "score": 0.8,
                    "status": "SURVIVOR",
                    "failed_gates": [],
                    "strategy_ir": snapshot,
                    "strategy_ir_hash": content_hash(snapshot),
                },
            ],
        },
    )
    store.append(
        "run", "run:new", {"research_run_id": "new", "requested_generations": 1, "seed": 2}
    )
    intent = ResearchIntent(
        mode="structure", parent_ids=(alternative.strategy_id,), operations=(), rationale="test"
    )
    with pytest.raises(ValueError, match="not an authorized parent"):
        select_intent_parent(source, intent, tmp_path, research_run_id="new")
    assert select_intent_parent(source, intent, tmp_path, research_run_id="old") == alternative
    assert (
        select_intent_parent(
            source,
            intent.model_copy(update={"parent_ids": (source.strategy_id,)}),
            tmp_path,
            research_run_id="new",
        )
        == source
    )


def test_research_parent_rejects_multiple_or_unknown_parents(tmp_path: Path) -> None:
    from research.llm.director import ResearchIntent
    from runtime.research_generation import select_intent_parent

    source = _source()
    for identifiers, expected in (
        (("missing",), "not an authorized parent"),
        ((source.strategy_id, "other"), "multi-parent"),
    ):
        intent = ResearchIntent(
            mode="structure", parent_ids=identifiers, rationale="test", operations=()
        )
        with pytest.raises(ValueError, match=expected):
            select_intent_parent(source, intent, tmp_path, research_run_id="new")


def test_unverified_best_strategy_payload_cannot_advance_research(tmp_path: Path) -> None:
    from runtime.research_loop import _strategy_from_evaluation

    fake = _source().model_copy(update={"strategy_id": "arbitrary-fake-successor"})
    result = {
        "status": "COMPLETED",
        "research_run_id": "run-a",
        "attempt_id": "try1",
        "best_strategy": fake.model_dump(mode="json", by_alias=True),
    }
    assert _strategy_from_evaluation(result, tmp_path, research_run_id="run-a") is None


def test_only_eligible_immutable_attempt_snapshot_advances_research(tmp_path: Path) -> None:
    from core.integrity.hashes import content_hash
    from runtime.research_loop import _strategy_from_evaluation

    eligible = _source().model_copy(update={"strategy_id": "audited-successor"})
    ir = eligible.model_dump(mode="json", by_alias=True)
    store = EvidenceStore(tmp_path)
    store.append("run", "run:a", {"research_run_id": "a", "requested_generations": 1, "seed": 2})
    store.append(
        "attempt",
        "attempt:try1",
        {
            "research_run_id": "a",
            "attempt_id": "try1",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "c1",
                    "family": eligible.family,
                    "score": 0.6,
                    "status": "SURVIVOR",
                    "failed_gates": [],
                    "strategy_ir": ir,
                    "strategy_ir_hash": content_hash(ir),
                }
            ],
        },
    )
    result = {
        "status": "COMPLETED",
        "research_run_id": "a",
        "attempt_id": "try1",
        "best_strategy": ir,
    }
    assert _strategy_from_evaluation(result, tmp_path, research_run_id="a") == eligible
    assert _strategy_from_evaluation(result, tmp_path, research_run_id="b") is None
    assert (
        _strategy_from_evaluation({**result, "attempt_id": "forged"}, tmp_path, research_run_id="a")
        is None
    )
    assert (
        _strategy_from_evaluation(
            {**result, "best_strategy": {**ir, "id": "tampered"}}, tmp_path, research_run_id="a"
        )
        is None
    )
