"""Recover a live Quant checkpoint in a new chat without a remembered session ID."""

from pathlib import Path

from core.data.parquet import ParquetDataProvider
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from integrations.codex_mcp_core import create_mcp_server
from integrations.mcp_context_budget import compact_mcp_context, encoded_size
from tests.research.test_academic_algorithm_plan import _market
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _server(tmp_path: Path):
    root = tmp_path / "project"
    (root / "data").mkdir(parents=True)
    ParquetDataProvider.write(root / "data" / "study.parquet", _market())
    return create_mcp_server(project_root=root, state_dir=tmp_path / "state")


def test_no_db_does_not_invent_progress(tmp_path):
    handoff = _server(tmp_path)._dispatch("get_research_brief", {})["algorithm_research_handoff"]
    assert handoff["status"] == "NO_ACTIVE_RESEARCH"
    assert handoff["active_count"] == 0
    assert handoff["selected_session_id"] is None
    assert handoff["next_read"] is None


def test_resumes_latest_session_without_chat_id(tmp_path):
    server = _server(tmp_path)
    created = server._dispatch(
        "start_algorithm_research", {"data_path": "data/study.parquet", "generations": 40}
    )
    sid = created["session_id"]
    handoff = server._dispatch("get_research_brief", {})["algorithm_research_handoff"]
    assert handoff["status"] == "RESUMABLE"
    assert handoff["selected_session_id"] == sid
    assert handoff["requested_generations"] == 40
    assert handoff["completed_generations"] == 0
    assert handoff["checkpoint_phase"] == "AWAITING_PLAN"
    assert handoff["output_contract"] == "AlgorithmPlan"
    assert handoff["next_checkpoint_action"] == "AUTHOR_AND_SUBMIT_PLAN"
    assert handoff["next_read"] == {
        "tool": "get_algorithm_research",
        "session_id": sid,
        "response_mode": "compact",
    }
    assert handoff["history_sample"] == []
    assert "checkpoint_token" not in handoff
    assert encoded_size(handoff) < 8192
    assert handoff["orders_enabled"] is False
    original = server._dispatch("get_algorithm_research", {"session_id": sid})
    assert original["checkpoint_token"] == created["checkpoint_token"]
    assert "algorithm_plan_schema" in original["model_context"]


def test_a_measured_generation_retains_real_hash_without_full_history(tmp_path):
    server = _server(tmp_path)
    started = server._dispatch(
        "start_algorithm_research", {"data_path": "data/study.parquet", "generations": 40}
    )
    sid = started["session_id"]
    llm = ScriptedResearcher()
    staged = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": sid,
            "checkpoint_token": started["checkpoint_token"],
            "plan": llm.propose(started["model_context"]),
        },
    )
    committed = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": sid,
            "checkpoint_token": staged["checkpoint_token"],
            "diagnosis": llm.propose(staged["model_context"]),
        },
    )
    assert committed["completed_generations"] == 1
    first = server._dispatch("get_research_brief", {})["algorithm_research_handoff"]
    assert first["completed_generations"] == 1
    assert first["last_evidence_hash"] == committed["history"][-1]["evidence_hash"]
    assert first["history_sample"][-1]["generation"] == 1
    assert first["latest_experiments"]["measured_count"] >= 1
    assert first["output_contract"] in {"AlgorithmPlan", "InheritedResearchIntent"}
    assert "checkpoint_token" not in first
    assert "algorithm_plan_schema" not in str(first)
    assert first == server._dispatch("get_research_brief", {})["algorithm_research_handoff"]
    assert encoded_size(first) < 8192


def test_multiple_active_sessions_do_not_guess_which_to_resume(tmp_path):
    server = _server(tmp_path)
    a = server._dispatch(
        "start_algorithm_research", {"data_path": "data/study.parquet", "generations": 10}
    )
    b = server._dispatch(
        "start_algorithm_research", {"data_path": "data/study.parquet", "generations": 40}
    )
    handoff = server._dispatch("get_research_brief", {})["algorithm_research_handoff"]
    assert handoff["status"] == "SELECTION_REQUIRED"
    assert handoff["selected_session_id"] is None
    assert handoff["next_read"] is None
    assert {s["session_id"] for s in handoff["active_sessions"]} == {
        a["session_id"],
        b["session_id"],
    }
    assert "checkpoint_token" not in handoff


def test_large_brief_keeps_handoff_in_summary():
    handoff = {
        "status": "RESUMABLE",
        "selected_session_id": "a" * 32,
        "next_read": {
            "tool": "get_algorithm_research",
            "session_id": "a" * 32,
            "response_mode": "compact",
        },
    }
    original = {
        "orders_enabled": False,
        "algorithm_research_handoff": handoff,
        "feature_catalog": [{"name": str(i), "note": "X" * 900} for i in range(200)],
        "research_trial_inventory": [{"id": str(i), "note": "x" * 900} for i in range(100)],
    }
    compact = compact_mcp_context("get_research_brief", original)
    assert compact["algorithm_research_handoff"] == handoff
    assert encoded_size(compact) <= 24576


def test_approved_32_tool_abi_unchanged():
    tools = chatgpt_tools()
    assert len(tools) == 32
    brief = next(x for x in tools if x["name"] == "get_research_brief")
    assert brief["inputSchema"]["properties"] == {
        "response_mode": {"type": "string", "enum": ["summary", "full"], "default": "summary"}
    }


def test_staged_diagnosis_survives_new_chat_without_repeating_plan(tmp_path):
    server = _server(tmp_path)
    started = server._dispatch(
        "start_algorithm_research",
        {
            "data_path": "data/study.parquet",
            "generations": 40,
        },
    )
    proposal = ScriptedResearcher().propose(started["model_context"])
    stage = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": proposal,
        },
    )
    handoff = server._dispatch("get_research_brief", {})["algorithm_research_handoff"]
    assert handoff["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    assert handoff["next_checkpoint_action"] == "AUTHOR_AND_SUBMIT_DIAGNOSIS"
    assert handoff["output_contract"] == "DiagnosticResponse"
    assert handoff["completed_generations"] == 0
    assert handoff["selected_session_id"] == started["session_id"]
    fresh = server._dispatch("get_algorithm_research", {"session_id": started["session_id"]})
    assert fresh["checkpoint_token"] == stage["checkpoint_token"]
    assert fresh["model_context"]["schema"] == "research-diagnostic-context-v1"


def test_interrupted_stage_never_retries_writes_blindly(tmp_path):
    import sqlite3

    server = _server(tmp_path)
    started = server._dispatch(
        "start_algorithm_research",
        {
            "data_path": "data/study.parquet",
            "generations": 40,
        },
    )
    with sqlite3.connect(tmp_path / "state" / "academic-gpt-checkpoints" / "gateway.sqlite") as db:
        db.execute(
            "UPDATE stages SET phase='INTERRUPTED' WHERE session_id=?", (started["session_id"],)
        )
    handoff = server._dispatch("get_research_brief", {})["algorithm_research_handoff"]
    assert handoff["status"] == "OPERATOR_RECOVERY_REQUIRED"
    assert handoff["next_checkpoint_action"] == "EXPLICIT_RECONCILIATION_AFTER_WORKER_STOP"
    assert "checkpoint_token" not in handoff
    assert handoff["completed_generations"] == 0


def test_terminal_sessions_can_be_located_for_reports_without_autoresume(tmp_path):
    server = _server(tmp_path)
    started = server._dispatch(
        "start_algorithm_research",
        {
            "data_path": "data/study.parquet",
            "generations": 1,
        },
    )
    llm = ScriptedResearcher()
    stage = server._dispatch(
        "submit_algorithm_plan",
        {
            "session_id": started["session_id"],
            "checkpoint_token": started["checkpoint_token"],
            "plan": llm.propose(started["model_context"]),
        },
    )
    done = server._dispatch(
        "submit_algorithm_diagnosis",
        {
            "session_id": started["session_id"],
            "checkpoint_token": stage["checkpoint_token"],
            "diagnosis": llm.propose(stage["model_context"]),
        },
    )
    assert done["status"] == "COMPLETED"
    handoff = server._dispatch("get_research_brief", {})["algorithm_research_handoff"]
    assert handoff["status"] == "NO_ACTIVE_RESEARCH"
    assert handoff["selected_session_id"] is None
    assert handoff["recent_terminal_sessions"][0]["session_id"] == started["session_id"]
    assert handoff["recent_terminal_sessions"][0]["completed_generations"] == 1
