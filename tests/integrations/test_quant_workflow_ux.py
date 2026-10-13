"""Scripted natural-language intent journeys over the actual ChatGPT MCP SDK plane.

These are five automated journeys, NOT five human-user usability tests.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from mcp.types import CallToolRequestParams

from application.research_batch_service import ResearchBatchService
from integrations.chatgpt_mcp_sdk import chatgpt_tools, create_chatgpt_sdk_adapter
from memory.evidence_store import EvidenceStore
from tests.integrations.test_batch_resume import _interrupted_after_first, _queued
from tests.integrations.test_gpt_guided_research import proposal
from tests.integrations.test_gpt_research_batches import _request
from tests.orchestration.test_evaluation_runner import _write_inputs


def _call(
    adapter: Any, tool: str, args: dict[str, Any] | None = None
) -> tuple[dict[str, Any], bool]:
    async def execute() -> tuple[dict[str, Any], bool]:
        response = await adapter.call_tool(
            None,
            CallToolRequestParams(name=tool, arguments=args or {}),
        )
        return json.loads(response.content[0].text), bool(response.is_error)

    return asyncio.run(execute())


def _make(tmp_path: Path) -> Any:
    _write_inputs(tmp_path)
    return create_chatgpt_sdk_adapter(state_dir=tmp_path / "state", project_root=tmp_path)


def test_journey_1_discover_readiness_and_detect_cached_schema(tmp_path: Path) -> None:
    """'QQQ 전략 연구 가능한지 먼저 확인해 줘.'"""
    adapter = _make(tmp_path)
    brief, error = _call(adapter, "get_research_brief")
    assert not error
    catalog = brief["mcp_capabilities"]
    assert catalog["server_tool_count"] == len(chatgpt_tools()) == 24
    assert catalog["schema_sha256"] and len(catalog["schema_sha256"]) == 64
    assert {"resume_research_batch", "reconcile_guided_research", "audit_market_data"} <= set(
        catalog["required_client_tools"]
    )
    assert "reconnect" in catalog["stale_client_hint"].lower()
    assert brief["_contract"]["orders_enabled"] is False
    assert brief["research_inputs"]["data_paths"] == ["bars.parquet"]
    assert not ResearchBatchService(
        project_root=tmp_path, state_dir=tmp_path / "state"
    ).database.exists()


def test_journey_2_invalid_input_then_corrected_preflight_no_side_effects(
    tmp_path: Path,
) -> None:
    """'실행 전에 QQQ 데이터/전략을 검사해 줘.'"""
    adapter = _make(tmp_path)
    first, error = _call(
        adapter,
        "preflight_research_batch",
        {
            **_request(),
            "data_path": "wrong-file.parquet",
        },
    )
    assert error and first["error_code"] == "DATA_FILE_NOT_FOUND"
    assert "get_research_brief" in first["message"]
    corrected, error = _call(adapter, "preflight_research_batch", _request())
    assert not error and corrected["preview_only"] is True
    assert corrected["dataset"]["zone"] == "development"
    assert corrected["orders_enabled"] is False
    assert not ResearchBatchService(
        project_root=tmp_path, state_dir=tmp_path / "state"
    ).database.exists()


def test_journey_3_run_status_and_final_evidence_report(tmp_path: Path) -> None:
    """'2세대만 모의 연구하고 결과와 이유를 보여 줘.'"""
    adapter = _make(tmp_path)
    started, error = _call(adapter, "start_research_batch", _request())
    assert not error
    job = started["job_id"]
    assert started["next_action"] == "POLL_STATUS"
    for _ in range(170):
        current, error = _call(adapter, "get_research_batch_status", {"job_id": job})
        assert not error
        if current["status"] not in {"QUEUED", "RUNNING"}:
            break
        time.sleep(0.15)
    assert current["status"] == "COMPLETED"
    assert current["next_action"] == "READ_FINAL_REPORT"
    cancel, cancel_error = _call(adapter, "cancel_research_batch", {"job_id": job})
    assert not cancel_error
    assert cancel["cancel_requested"] is False
    assert cancel["cancellation_request_accepted"] is False
    assert cancel["status"] == "COMPLETED"
    final, error = _call(adapter, "get_research_batch_report", {"job_id": job})
    assert not error and final["final_report_ready"] is True
    assert final["oos_approved"] is False
    assert final["orders_enabled"] is False
    evidence, error = _call(
        adapter,
        "get_research_evidence",
        {
            "research_run_id": current["research_run_id"],
        },
    )
    assert not error
    assert evidence["status"] == "OK"
    assert (
        len([e for e in EvidenceStore(tmp_path / "state").events() if e["kind"] == "generation"])
        == current["completed_generations"]
    )


def test_journey_4_interruption_resume_failure_code_and_same_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """'중단된 3세대 연구를 완료된 세대부터 안전하게 이어서 실행해 줘.'"""
    adapter = _make(tmp_path)
    svc = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    job = _queued(
        svc,
        {
            **_request(generations=3),
            "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4, 5]}],
        },
    )
    _interrupted_after_first(svc, job, monkeypatch)
    before = EvidenceStore(tmp_path / "state").events()
    old_run = svc.status(job)["research_run_id"]
    status, error = _call(adapter, "get_research_batch_status", {"job_id": job})
    assert not error and status["status"] == "INTERRUPTED"
    assert status["next_action"] == "REVIEW_AND_RESUME"
    with monkeypatch.context() as mp:
        mp.setattr(ResearchBatchService, "_spawn_worker", lambda self, jid: None)
        accepted, error = _call(adapter, "resume_research_batch", {"job_id": job})
    assert not error
    assert accepted["resumed_from_generation"] == 1
    svc.execute(job)
    final, error = _call(adapter, "get_research_batch_report", {"job_id": job})
    assert not error and final["status"] == "COMPLETED"
    assert final["research_run_id"] == old_run
    assert final["orders_enabled"] is False
    events = EvidenceStore(tmp_path / "state").events()
    assert events[: len(before)] == before
    duplicate, rejected = _call(adapter, "resume_research_batch", {"job_id": job})
    assert rejected and duplicate["error_code"] == "BATCH_NOT_INTERRUPTED"
    assert "completed" in duplicate["message"].lower()


def test_journey_5_guided_checkpoint_duplicate_and_explicit_completion(
    tmp_path: Path,
) -> None:
    """'GPT가 실패 원인을 보고 다음 세대 전략을 바꿔 평가해 줘.'"""
    adapter = _make(tmp_path)
    created, error = _call(
        adapter,
        "start_guided_research",
        {
            "data_path": "bars.parquet",
            "generations": 2,
            "method": "grid",
            "count": 1,
            "seed": 25,
        },
    )
    assert not error and created["status"] == "AWAITING_GPT"
    first, error = _call(
        adapter,
        "submit_guided_generation",
        {
            "session_id": created["session_id"],
            "checkpoint_token": created["checkpoint_token"],
            "generation": 1,
            **proposal(),
        },
    )
    assert not error and first["status"] == "AWAITING_GPT"
    repeated, rejected = _call(
        adapter,
        "submit_guided_generation",
        {
            "session_id": created["session_id"],
            "checkpoint_token": first["checkpoint_token"],
            "generation": 2,
            **proposal(),
        },
    )
    assert rejected
    assert repeated["orders_enabled"] is False
    point, error = _call(
        adapter,
        "get_guided_research",
        {
            "session_id": created["session_id"],
        },
    )
    assert not error and point["checkpoint_token"] == first["checkpoint_token"]
    final, error = _call(
        adapter,
        "submit_guided_generation",
        {
            "session_id": created["session_id"],
            "checkpoint_token": point["checkpoint_token"],
            "generation": 2,
            "source_path": "strategy.yaml",
            "intent": {
                **proposal()["intent"],
                "operations": [
                    {
                        "op": "REPLACE_RULE",
                        "path": "entry.conditions.0",
                        "condition": {"op": "greater_than", "left": "close", "value": 102},
                    }
                ],
            },
        },
    )
    assert not error and final["status"] == "COMPLETED"
    assert final["history"][1]["previous_run_id"] == final["history"][0]["run_id"]
    assert final["orders_enabled"] is False


def test_pending_cancellation_ack_is_distinct_from_terminal_cancellation(tmp_path: Path) -> None:
    """An accepted cancel flag is not a claim that the detached worker has stopped."""
    adapter = _make(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    job = _queued(service, _request(generations=3))
    first, error = _call(adapter, "cancel_research_batch", {"job_id": job})
    assert not error
    assert first["status"] == "QUEUED"
    assert first["cancel_requested"] is True
    assert first["cancellation_request_accepted"] is True
    assert first["next_action"] == "WAIT_FOR_CANCELLATION"
    repeated, error = _call(adapter, "cancel_research_batch", {"job_id": job})
    assert not error
    assert repeated["cancel_requested"] is True
    assert repeated["cancellation_request_accepted"] is False
    assert repeated["status"] == "QUEUED"
    assert EvidenceStore(tmp_path / "state").events() == []
