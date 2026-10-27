"""Test-only read-through from fast batches into the existing GPT researcher."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from memory.evidence_store import EvidenceStore
from research.llm.batch_learning_handoff import recent_batch_learning


def _seed(state: Path) -> tuple[Path, str]:
    db_path = state / "system" / "gpt-research-batches.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    run = "a" * 32
    job = "b" * 32
    with sqlite3.connect(db_path) as c:
        c.executescript("""
        CREATE TABLE batches(id TEXT PRIMARY KEY,status TEXT,request_json TEXT,requested INTEGER,
           completed INTEGER,created REAL,started REAL,finished REAL,pid INTEGER,heartbeat REAL,
           cancel INTEGER,research_run_id TEXT,error_code TEXT);
        CREATE TABLE generation_history(batch_id TEXT,generation INTEGER,seconds REAL,method TEXT,
           count INTEGER,parent_id TEXT,successor_id TEXT,result_status TEXT,
           result_counts TEXT,candidate_count INTEGER,
           PRIMARY KEY(batch_id,generation));
        """)
        c.execute(
            "INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                job,
                "COMPLETED",
                json.dumps({"intent": {"mode": "parameter"}}),
                1,
                1,
                1.0,
                1.0,
                2.0,
                None,
                2.0,
                0,
                run,
                None,
            ),
        )
        c.execute(
            "INSERT INTO generation_history VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                job,
                1,
                0.5,
                "random",
                1,
                "mean_reversion",
                "mean_reversion",
                "COMPLETED",
                json.dumps({"REJECT": 1, "DUPLICATE_SKIPPED": 0}),
                1,
            ),
        )
    store = EvidenceStore(state)
    store.append(
        "run",
        f"run:{run}",
        {
            "research_run_id": run,
            "requested_generations": 1,
            "seed": 1,
            "settings": {"job_id": job, "fixed_research_intent": True},
        },
    )
    store.append(
        "manifest",
        f"manifest:{run}",
        {
            "research_run_id": run,
            "comparison_key": "same-dev",
            "data_zone": "development",
            "dataset_hash": "test-data",
            "market_data_quality": {"point_in_time_verified": False, "status": "UNVERIFIED"},
        },
    )
    store.append(
        "attempt",
        "attempt:one",
        {
            "research_run_id": run,
            "attempt_id": "one",
            "generation": 1,
            "status": "COMPLETED",
            "candidates": [
                {
                    "candidate_hash": "c" * 64,
                    "dataset_hash": "test-data",
                    "status": "REJECT",
                    "family": "reversal",
                    "full_cagr": 0.12,
                    "max_drawdown": 0.30,
                    "trade_count": 12,
                    "failed_gates": ["annual_trade_count", "validation"],
                    "parameters": {"risk.stop_loss_pct": 3},
                }
            ],
        },
    )
    store.append(
        "generation",
        f"generation:{run}:1",
        {
            "research_run_id": run,
            "generation": 1,
            "status": "COMPLETED",
            "attempt_id": "one",
            "duplicate_skipped": 0,
        },
    )
    store.append("end", f"end:{run}", {"research_run_id": run, "status": "COMPLETED"})
    return db_path, run


def test_rejects_are_memory_not_promotions(tmp_path: Path) -> None:
    db, run = _seed(tmp_path)
    before = db.read_bytes()
    context = recent_batch_learning(tmp_path)
    assert context["status"] == "VERIFIED_DEVELOPMENT_MEMORY"
    assert context["candidate_promotion_authorized"] is False
    assert context["per_generation_llm_evolution_verified"] is False
    assert context["batches"][0]["research_run_id"] == run
    assert context["batches"][0]["evaluated"] == 1
    assert context["batches"][0]["rejected"] == 1
    assert context["batches"][0]["top_failure_gates"] == [
        {"gate": "annual_trade_count", "count": 1},
        {"gate": "validation", "count": 1},
    ]
    assert context["batches"][0]["best_rejected_research_hint"]["cagr"] == 0.12
    assert db.read_bytes() == before


def test_fail_closed_for_missing_evidence_or_counter_mismatch(tmp_path: Path) -> None:
    db, _ = _seed(tmp_path)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE batches SET completed=2")
    x = recent_batch_learning(tmp_path)
    assert x["status"] == "EVIDENCE_UNVERIFIED"
    assert x["batches"] == []
    with sqlite3.connect(db) as c:
        c.execute("UPDATE batches SET completed=1")
    (tmp_path / "system" / "research-evidence" / "evidence.sqlite").rename(
        tmp_path / "missing.sqlite"
    )
    y = recent_batch_learning(tmp_path)
    assert y["status"] == "EVIDENCE_UNVERIFIED"
    assert y["batches"] == []


def test_absent_database_never_invents_learning(tmp_path: Path) -> None:
    assert recent_batch_learning(tmp_path)["status"] == "NO_BOUNDED_BATCHES"


def test_handoff_attaches_to_original_gpt_checkpoint_without_changing_plan_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from integrations import codex_mcp_core as core

    _seed(tmp_path)
    model_context = {"context_hash": "unchanged-checkpoint-proof", "schema": "existing-plan"}

    class ExistingGPTCheckpoint:
        def __init__(self, **_kwargs):
            pass

        def get(self, _args):
            return {
                "checkpoint_phase": "AWAITING_PLAN",
                "model_context": model_context.copy(),
                "completed_generations": 83,
                "requested_generations": 100,
            }

    monkeypatch.setattr(core, "AcademicMCPCheckpointService", ExistingGPTCheckpoint)
    server = object.__new__(core.CodexMCPServer)
    server.state_dir = tmp_path
    server.project_root = tmp_path
    server.parent_portfolio_v2_session_id = ""
    result = server._dispatch("get_algorithm_research", {"session_id": "f" * 32})
    assert result["model_context"] == model_context
    assert result["bounded_batch_research_memory"]["status"] == "VERIFIED_DEVELOPMENT_MEMORY"
    assert result["completed_generations"] == 83
    assert result["bounded_batch_research_memory"]["candidate_promotion_authorized"] is False


def test_research_brief_includes_bounded_failure_memory_without_tool_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    from integrations import codex_mcp_core as core
    from integrations.mcp_context_budget import compact_mcp_context

    _seed(tmp_path)
    server = object.__new__(core.CodexMCPServer)
    server.state_dir = tmp_path
    server.project_root = tmp_path
    server.services = SimpleNamespace(research=SimpleNamespace(brief=lambda: {"status": "READY"}))
    monkeypatch.setattr(core.ResearchBatchService, "describe_inputs", lambda _self: {"sources": []})
    monkeypatch.setattr(core, "research_trial_inventory", lambda _paths: {"record_count": 0})
    reply = server._dispatch("get_research_brief", {})
    assert reply["bounded_batch_research_memory"]["status"] == "VERIFIED_DEVELOPMENT_MEMORY"
    assert reply["mcp_capabilities"]["server_tool_count"] == 32
    reply["observations"] = ["historical analysis"] * 4000
    projected = compact_mcp_context("get_research_brief", reply, limit_bytes=24 * 1024)
    assert projected["bounded_batch_research_memory"] == reply["bounded_batch_research_memory"]
    assert projected["bounded_batch_research_memory"]["candidate_promotion_authorized"] is False
