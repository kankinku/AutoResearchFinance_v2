"""Verify index queries are reproducible and grounded, not memory-generated advice."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from application.research_handoff_builder import build_research_handoff
from research.llm.evidence_memory_retrieval import (
    MemoryRetrievalError,
    search_evidence_memory,
)
from tests.research.test_evidence_handoff_m0 import _history_fixture


def test_parent_and_status_search_preserves_hash_evidence(tmp_path: Path):
    _, state, receipts = _history_fixture(tmp_path)
    handoff = build_research_handoff(state, receipts)
    event = handoff["events"][0]
    parent = event["experiments"][0]["parent_strategy_hash"]
    first = search_evidence_memory(handoff, parent_hash=parent, limit=10)
    assert first == search_evidence_memory(handoff, parent_hash=parent, limit=10)
    assert first["results"]
    assert all(e["parent_strategy_hash"] == parent for e in first["results"])
    assert all(
        e["event_hash"] in [x["event_hash"] for x in handoff["events"]] for e in first["results"]
    )
    assert first["not_evidence_of_causality"] is True
    negative = search_evidence_memory(handoff, only_negative=True)
    assert all(x["finding"] != "DIRECTION_MATCHED_DEVELOPMENT_ONLY" for x in negative["results"])
    assert negative["source_handoff_hash"] == handoff["handoff_hash"]


def test_small_limit_returns_unresolved_count_and_requires_replay(tmp_path: Path):
    _, state, receipts = _history_fixture(tmp_path)
    handoff = build_research_handoff(state, receipts)
    result = search_evidence_memory(handoff, limit=1)
    assert len(result["results"]) == 1
    assert result["total_matches"] >= 2
    assert result["more_evidence_requires_lookup"] is True
    assert result["safe_as_complete_memory"] is False


def test_invalid_index_input_and_tampered_derivation_fail_closed(tmp_path: Path):
    _, state, receipts = _history_fixture(tmp_path)
    handoff = build_research_handoff(state, receipts)
    edited = deepcopy(handoff)
    edited["events"][0]["experiments"][0]["finding"] = "FAKE"
    with pytest.raises(MemoryRetrievalError, match="handoff|event"):
        search_evidence_memory(edited)
    with pytest.raises(MemoryRetrievalError, match="parent"):
        search_evidence_memory(handoff, parent_hash="not-a-hash")
    with pytest.raises(MemoryRetrievalError, match="limit"):
        search_evidence_memory(handoff, limit=0)


@pytest.mark.parametrize(
    "key",
    [
        "NO_OBSERVED_EFFECT",
        "DIRECTION_MATCHED_DEVELOPMENT_ONLY",
        "DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY",
        "DEGENERATE_INACTIVE_CHILD",
    ],
)
def test_finding_filters_are_exact_never_llm_semantic_similarity(tmp_path: Path, key: str):
    _, state, receipts = _history_fixture(tmp_path)
    handoff = build_research_handoff(state, receipts)
    result = search_evidence_memory(handoff, finding=key)
    assert all(x["finding"] == key for x in result["results"])
    assert result["query"]["finding"] == key


def test_50_grounding_questions_measured_on_real_quant_2gen_fixture(tmp_path: Path):
    from research.llm.evidence_memory_retrieval import audit_evidence_grounding

    _, state, receipts = _history_fixture(tmp_path)
    handoff = build_research_handoff(state, receipts)
    report = audit_evidence_grounding(handoff, state, receipts)
    assert report["questions"] >= 50
    assert report["passed"] == report["questions"]
    assert report["failed"] == 0
    assert report["real_gpt_calls"] == 0
    assert report["data_scope"] == "ISOLATED_NON_PIT_DEVELOPMENT"
