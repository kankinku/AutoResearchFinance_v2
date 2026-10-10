"""GPT-authored, detached, durable N-generation evaluation and measured ETA."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from application.research_batch_service import ResearchBatchService
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from memory.evidence_store import EvidenceStore
from tests.orchestration.test_evaluation_runner import _write_inputs


def _request(*, generations: int = 2) -> dict[str, object]:
    return {
        "source_path": "strategy.yaml",
        "data_path": "bars.parquet",
        "intent": {
            "mode": "structure",
            "parent_ids": ["runner-test"],
            "operations": [],
            "rationale": "GPT initial validated strategy plan",
        },
        "generations": generations,
        "count": 1,
        "method": "random",
        "seed": 8,
        "min_trades": 0,
        "min_annual_trades": 0,
        "min_qqq_cagr_delta": 0.0,
    }


def test_gpt_batch_tools_are_visible_but_canonical_server_contract_is_unchanged() -> None:
    from integrations.codex_mcp_core import _tools

    assert len(_tools()) == 13
    names = {item["name"] for item in chatgpt_tools()}
    assert {
        "start_research_batch",
        "get_research_batch_status",
        "get_research_batch_report",
        "cancel_research_batch",
    } <= names
    assert {"start_system", "stop_system", "run_evaluation"}.isdisjoint(names)


def test_gpt_batch_runs_two_generations_and_reuses_history_for_eta(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    state = tmp_path / "state"
    service = ResearchBatchService(project_root=tmp_path, state_dir=state)
    assert service.database.exists() is False
    first = service.start(_request())
    jid = str(first["job_id"])
    assert first["status"] in {"QUEUED", "RUNNING"}
    assert first["eta_basis"] == "insufficient_data"
    for _ in range(100):
        time.sleep(0.2)
        status = service.status(jid)
        if status["status"] not in {"QUEUED", "RUNNING"}:
            break
    assert status["status"] == "COMPLETED", status
    report = service.report(jid)
    assert report["final_report_ready"] is True
    assert report["completed_generations"] == 2
    assert report["oos_approved"] is False
    assert len(report["generations"]) == 2
    assert all(float(item["duration_seconds"]) > 0 for item in report["generations"])
    assert report["total_measured_seconds"] > 0
    assert report["evaluated_candidate_instances"] >= 1
    assert report["unique_candidate_count"] is not None
    assert report["duplicate_candidate_evaluations"] == (
        report["evaluated_candidate_instances"] - report["unique_candidate_count"]
    )
    assert report["candidate_uniqueness_basis"] == "immutable_evidence"
    assert report["research_intent_mode"] == "fixed_intent"
    assert report["promoted_successor_generations"] >= 0
    assert len([x for x in EvidenceStore(state).events() if x["kind"] == "generation"]) == 2
    second = service.start(_request(generations=1))
    assert second["eta_basis"] == "historical"
    assert float(second["estimated_seconds_per_generation"]) > 0
    for _ in range(100):
        time.sleep(0.2)
        s = service.status(str(second["job_id"]))
        if s["status"] not in {"QUEUED", "RUNNING"}:
            break
    assert s["status"] == "COMPLETED", s


def test_batch_validation_rejects_invalid_intents_and_generation_bounds(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    for args in (
        _request(generations=0),
        _request(generations=101),
        {**_request(), "intent": {**_request()["intent"], "parent_ids": ["forged"]}},
        {**_request(), "python_patch": "dangerous"},
    ):
        with pytest.raises(ValueError):
            service.start(args)
    assert not service.database.exists()


def test_batch_parameter_domains_produce_distinct_audited_candidates(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    request = {
        **_request(generations=1),
        "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4]}],
        "count": 3,
    }
    started = service.start(request)
    jid = str(started["job_id"])
    for _ in range(150):
        time.sleep(0.2)
        status = service.status(jid)
        if status["status"] not in {"QUEUED", "RUNNING"}:
            break
    assert status["status"] == "COMPLETED", status
    report = service.report(jid)
    assert report["evaluated_candidate_instances"] == 3
    assert report["unique_candidate_count"] == 3
    assert report["duplicate_candidate_evaluations"] == 0
    assert report["repeated_candidate_warning"] is False
    assert report["generations"][0]["candidate_count"] == 3


@pytest.mark.parametrize(
    "domain",
    [
        {"name": "entry.logic", "values": ["AND", "OR"]},
        {"name": "indicators.fast.type", "values": ["SMA", "EMA"]},
        {"name": "indicators.missing.period", "values": [3, 4]},
        {"name": "indicators.fast.period", "values": [2] * 25},
    ],
)
def test_batch_rejects_invalid_parameter_domains_before_job_creation(
    tmp_path: Path, domain: dict[str, object]
) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    with pytest.raises(ValueError):
        service.start({**_request(), "parameter_domains": [domain]})
    assert not service.database.exists()
