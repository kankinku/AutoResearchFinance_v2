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


def test_restores_only_hash_checked_ir_of_eligible_frontier_parents(tmp_path: Path) -> None:
    from core.integrity.hashes import content_hash
    from memory.evidence_frontier import frontier_parents
    from strategy_ir.schema import StrategyIR
    from tests.orchestration.test_train_only_selection import strategy

    original = strategy()
    snapshot = original.model_dump(mode="json", by_alias=True)
    store = EvidenceStore(tmp_path)
    store.append("run", "run:ir", {"research_run_id": "ir", "requested_generations": 1, "seed": 1})
    candidates = [
        {
            "candidate_hash": "safe",
            "family": "test",
            "score": 0.8,
            "status": "SURVIVOR",
            "failed_gates": [],
            "strategy_ir": snapshot,
            "strategy_ir_hash": content_hash(snapshot),
        },
        {
            "candidate_hash": "bad",
            "family": "other",
            "score": 0.9,
            "status": "SURVIVOR",
            "failed_gates": [],
            "strategy_ir": snapshot,
            "strategy_ir_hash": "wrong-hash",
        },
        {
            "candidate_hash": "near",
            "family": "near",
            "score": 0.99,
            "status": "NEAR_MISS",
            "failed_gates": ["return"],
            "strategy_ir": snapshot,
            "strategy_ir_hash": content_hash(snapshot),
        },
    ]
    store.append(
        "attempt",
        "attempt:ir",
        {
            "research_run_id": "ir",
            "attempt_id": "ir",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": candidates,
        },
    )
    parents = frontier_parents(tmp_path)
    assert len(parents) == 1
    assert isinstance(parents[0], StrategyIR)
    assert parents[0].strategy_id == original.strategy_id


def test_frontier_parents_legacy_evidence_returns_empty(tmp_path: Path) -> None:
    from memory.evidence_frontier import frontier_parents

    _append_attempts(tmp_path)
    assert frontier_parents(tmp_path) == ()


def test_runner_snapshot_record_only_contains_eligible_ir() -> None:
    from dataclasses import replace

    from core.integrity.hashes import content_hash
    from orchestration.evaluation_runner import _candidate_snapshot_evidence
    from tests.orchestration.test_train_only_selection import data, evaluate

    result = evaluate(data())
    candidate, outcome = result.candidates[0], result.funnel[0]
    survivor = _candidate_snapshot_evidence(candidate, replace(outcome, status="SURVIVOR"))
    assert survivor["strategy_ir_hash"] == content_hash(survivor["strategy_ir"])
    assert survivor["strategy_ir"]["id"] == candidate.strategy.strategy_id
    near_miss = _candidate_snapshot_evidence(candidate, replace(outcome, status="NEAR_MISS"))
    assert "strategy_ir" not in near_miss
    assert "strategy_ir_hash" not in near_miss
