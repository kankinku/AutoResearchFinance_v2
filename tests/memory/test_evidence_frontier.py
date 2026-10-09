"""Frontier context must be reconstructed from immutable research evidence."""

from __future__ import annotations

from pathlib import Path

from memory.evidence_frontier import frontier_summary
from memory.evidence_store import EvidenceStore
from orchestration.evaluation_runner import build_research_context


def _append_attempts(root: Path) -> None:
    store = EvidenceStore(root)
    store.append(
        "run", "run:test", {"research_run_id": "test", "requested_generations": 1, "seed": 9}
    )
    store.append(
        "attempt",
        "attempt:one",
        {
            "research_run_id": "test",
            "attempt_id": "one",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "m1",
                    "family": "momentum",
                    "score": 0.7,
                    "status": "SURVIVOR",
                    "failed_gates": [],
                },
                {
                    "candidate_hash": "m2",
                    "family": "momentum",
                    "score": 0.9,
                    "status": "SURVIVOR",
                    "failed_gates": [],
                },
                {
                    "candidate_hash": "v1",
                    "family": "value",
                    "score": 0.6,
                    "status": "NEAR_MISS",
                    "failed_gates": ["trade_count"],
                },
                {
                    "candidate_hash": "t1",
                    "family": "trend",
                    "score": 0.8,
                    "status": "SURVIVOR",
                    "failed_gates": [],
                },
            ],
        },
    )


def test_reconstructs_best_per_family_without_writing_mutable_snapshot(tmp_path: Path) -> None:
    _append_attempts(tmp_path)
    frontier = frontier_summary(tmp_path)
    assert [entry["candidate_hash"] for entry in frontier] == ["m2", "t1"]
    assert frontier[0]["score"] == 0.9
    assert not (tmp_path / "frontier.json").exists()


def test_research_director_context_includes_immutable_frontier(tmp_path: Path) -> None:
    _append_attempts(tmp_path)
    context = build_research_context(tmp_path)
    assert [entry["candidate_hash"] for entry in context["frontier"]] == ["m2", "t1"]
    assert "sealed_oos" not in str(context)
