"""Integration of evidence-bound paired training controls into Guided feedback."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

import pytest

from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from integrations.codex_mcp_core import CodexMCPServer
from memory.evidence_store import EvidenceIntegrityError
from research.llm.guided_controlled_development import controlled_training_comparison
from tests.integrations.test_guided_learning_loop_restore import _fixture, _submit


def test_rejected_child_triggers_real_training_paired_control_and_next_direction(tmp_path):
    service, point, source = _fixture(tmp_path)
    first = _submit(service, point, source, 90)
    c = first["controlled_training_memory"]
    assert first["completed_generations"] == 1
    assert c["verified_generations"] == 1
    assert c["causal_status"] == "NOT_ESTABLISHED" and c["sealed_oos_evaluated"] is False
    report = service.training_control({"session_id": point["session_id"], "generation": 1})
    assert report["training_bars"] < 1508 and report["training_bars"] > 100
    assert report["first_excluded_bar_at"] > report["training_end_at"]
    assert report["validation_fold_tests_used"] is False and report["sealed_oos_evaluated"] is False
    assert report["production_promotion"] is False
    assert report["training_dataset_hash"] != report["original_dataset_hash"]
    assert len(report["comparisons"]) == 1
    outcome = report["comparisons"][0]
    assert outcome["parent_fill_count"] > 0 and outcome["child_fill_count"] > 0
    assert outcome["parent_execution_trace_hash"] != outcome["child_execution_trace_hash"]
    assert len(outcome["development_windows"]) == 4
    assert outcome["causal_status"] == "NOT_ESTABLISHED"
    assert first["learning_feedback"]["failed_candidates_included"] == 1
    assert first["learning_feedback"]["production_promotions"] == 0
    assert first["controlled_training_memory"]["next_experiment_priority"]
    before = service.get(first["session_id"])
    repeat = service.training_control({"session_id": point["session_id"], "generation": 1})
    assert repeat["report_hash"] == report["report_hash"]
    assert service.get(first["session_id"])["checkpoint_token"] == before["checkpoint_token"]
    second = _submit(service, first, source, 75, research_parent_generation=1)
    assert second["completed_generations"] == 2
    assert second["controlled_training_memory"]["verified_generations"] == 2
    assert second["learning_feedback"]["failed_candidates_included"] == 2


def test_mcp_existing_get_guided_research_can_fetch_paired_control(tmp_path):
    service, point, source = _fixture(tmp_path)
    first = _submit(service, point, source, 90)
    server = CodexMCPServer(project_root=service.root, state_dir=service.state_dir)
    data = server._dispatch(
        "get_guided_research", {"session_id": first["session_id"], "controlled_generation": 1}
    )
    assert data["controlled_generation_report"]["generation"] == 1
    assert data["controlled_generation_report"]["sealed_oos_evaluated"] is False
    assert data["controlled_training_memory"]["verified_generations"] == 1
    with pytest.raises(ValueError, match="requires session_id,generation|CONTROL_ONLY_COMMITTED"):
        server._dispatch(
            "get_guided_research", {"session_id": first["session_id"], "controlled_generation": 3}
        )


def test_corrupted_control_report_stops_guided_next_feedback(tmp_path):
    service, point, source = _fixture(tmp_path)
    first = _submit(service, point, source, 90)
    with sqlite3.connect(service.db_path) as db:
        db.execute(
            "UPDATE guided_controlled_reports SET report_json=? WHERE session_id=?",
            ('{"changed":true}', first["session_id"]),
        )
    with pytest.raises(EvidenceIntegrityError, match="controlled report integrity"):
        service.get(first["session_id"])


def test_training_compare_rejects_sealed_oos_and_unverified_proposal(tmp_path):
    service, point, source = _fixture(tmp_path)
    first = _submit(service, point, source, 90)
    with sqlite3.connect(service.db_path) as db:
        raw = db.execute(
            "SELECT proposal_json,proposal_hash FROM guided_research_proposals WHERE session_id=?",
            (first["session_id"],),
        ).fetchone()
    p = json.loads(raw[0])
    evidence = service._learning_history(
        first["session_id"], service._read(first["session_id"])[0]["dataset_hash"]
    )[0]["attempt"]
    market = ParquetDataProvider.read(
        service.root / "data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet"
    )
    with pytest.raises(PermissionError, match="DEVELOPMENT_ONLY"):
        controlled_training_comparison(
            proposal=p,
            proposal_hash=raw[1],
            attempt=evidence,
            market=replace(market, zone=DataZone.SEALED_OOS),
            expected_run_id=p["run_id"],
        )
    with pytest.raises(ValueError, match="GUIDED_PROPOSAL_HASH_MISMATCH"):
        controlled_training_comparison(
            proposal={**p, "parent_semantic_hash": "0" * 64},
            proposal_hash=raw[1],
            attempt=evidence,
            market=market,
            expected_run_id=p["run_id"],
        )


def test_missing_control_blocks_next_generation_and_reconcile_repairs_without_evaluation(tmp_path):
    service, point, source = _fixture(tmp_path)
    first = _submit(service, point, source, 90)
    with sqlite3.connect(service.db_path) as db:
        db.execute(
            "DELETE FROM guided_controlled_reports WHERE session_id=?", (first["session_id"],)
        )
    before_run_count = len(
        [
            e
            for e in __import__("memory.evidence_store", fromlist=["EvidenceStore"])
            .EvidenceStore(service.state_dir)
            .events()
            if e["kind"] == "run"
        ]
    )
    with pytest.raises(ValueError, match="CONTROL_PREVIOUS_GENERATION_REQUIRED_CALL_RECONCILE"):
        _submit(service, first, source, 75, research_parent_generation=1)
    reconciled = service.reconcile(first["session_id"])
    assert reconciled["reconciliation"] == "ALREADY_SETTLED"
    assert reconciled["controlled_training_memory"]["verified_generations"] == 1
    after_run_count = len(
        [
            e
            for e in __import__("memory.evidence_store", fromlist=["EvidenceStore"])
            .EvidenceStore(service.state_dir)
            .events()
            if e["kind"] == "run"
        ]
    )
    assert before_run_count == after_run_count == 1
    second = _submit(service, reconciled, source, 75, research_parent_generation=1)
    assert second["completed_generations"] == 2
    assert second["controlled_training_memory"]["verified_generations"] == 2
