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
        "preflight_research_batch",
        "start_research_batch",
        "get_research_batch_status",
        "get_research_batch_report",
        "cancel_research_batch",
        "resume_research_batch",
    } <= names
    assert {"start_system", "stop_system", "run_evaluation"}.isdisjoint(names)


def test_batch_preflight_is_read_only_and_warns_on_repeated_candidates(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    result = service.preflight(_request(generations=5))
    assert result["status"] == "READY_WITH_WARNINGS"
    assert result["orders_enabled"] is False
    assert result["preview_generations"] == 5
    assert result["preview_candidate_instances"] == 5
    assert result["preview_unique_strategies"] == 1
    assert result["preview_duplicate_candidates"] == 4
    assert result["repetition_risk"] is True
    assert result["dataset"]["bars"] > 0
    assert result["dataset"]["zone"] == "development"
    assert not service.database.exists()


def test_batch_preflight_reports_unique_domain_preview(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    request = {
        **_request(generations=1),
        "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4]}],
        "count": 3,
    }
    result = service.preflight(request)
    assert result["status"] in {"READY", "READY_WITH_WARNINGS"}
    assert result["preview_candidate_instances"] == 3
    assert result["preview_unique_strategies"] == 3
    assert result["repetition_risk"] is False
    assert not service.database.exists()


def test_batch_preflight_fails_before_a_worker_on_invalid_parquet(tmp_path: Path) -> None:
    from application.research_batch_service import BatchRequestError

    _write_inputs(tmp_path)
    (tmp_path / "bars.parquet").write_bytes(b"not a parquet file")
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    with pytest.raises(BatchRequestError) as exc:
        service.start(_request())
    assert exc.value.code == "INVALID_DATASET"
    assert not service.database.exists()


def test_preflight_mcp_dispatch_is_read_only(tmp_path: Path) -> None:
    import asyncio
    import json

    from mcp.types import CallToolRequestParams

    from integrations.chatgpt_mcp_sdk import create_chatgpt_sdk_adapter

    _write_inputs(tmp_path)
    adapter = create_chatgpt_sdk_adapter(state_dir=tmp_path / "state", project_root=tmp_path)

    async def run() -> dict[str, object]:
        response = await adapter.call_tool(
            None,
            CallToolRequestParams(
                name="preflight_research_batch", arguments=_request(generations=5)
            ),
        )
        assert response.is_error is False
        return json.loads(response.content[0].text)

    report = asyncio.run(run())
    assert report["preview_unique_strategies"] == 1
    assert report["orders_enabled"] is False
    assert report["_contract"]["orders_enabled"] is False
    assert not (tmp_path / "state" / "system" / "gpt-research-batches.sqlite").exists()


def test_preflight_rejects_sealed_data_without_loading_rows(tmp_path: Path) -> None:
    from application.research_batch_service import BatchRequestError
    from core.data.contracts import DataZone, MarketDataSet
    from core.data.parquet import ParquetDataProvider

    _write_inputs(tmp_path)
    path = tmp_path / "bars.parquet"
    original = ParquetDataProvider.read(path)
    ParquetDataProvider.write(
        path,
        MarketDataSet(
            original.version,
            DataZone.SEALED_OOS,
            original.bars,
            original.timeframe,
            original.calendar,
            original.provenance,
        ),
    )
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    with pytest.raises(BatchRequestError) as exc:
        service.preflight(_request())
    assert exc.value.code == "DATA_ZONE_DENIED"
    assert not service.database.exists()


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
    analysis = report["failure_analysis"]
    assert analysis["source"] == "immutable_evidence"
    assert analysis["evaluated_candidate_instances"] == report["evaluated_candidate_instances"]
    assert analysis["data_quality"]["point_in_time_verified"] is False
    assert analysis["sealed_oos"] == "NOT_MEASURED"
    assert analysis["causal_status"] == "UNKNOWN"
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


def test_repeated_single_candidate_generation_is_skipped_with_evidence(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    state = tmp_path / "state"
    service = ResearchBatchService(project_root=tmp_path, state_dir=state)
    first = service.start(_request(generations=3))
    jid = str(first["job_id"])
    for _ in range(140):
        time.sleep(0.2)
        status = service.status(jid)
        if status["status"] not in {"QUEUED", "RUNNING"}:
            break
    assert status["status"] == "COMPLETED", status
    report = service.report(jid)
    assert report["completed_generations"] == 2
    assert report["requested_generations"] == 3
    assert report["stopped_early"] is True
    assert report["stop_reason"] == "SEARCH_SPACE_EXHAUSTED"
    assert report["unexecuted_generations"] == 1
    assert report["skipped_duplicate_generations"] == 1
    assert report["total_skipped_duplicate_candidates"] == 1
    assert [row["status"] for row in report["generations"]] == [
        "COMPLETED",
        "NO_NEW_CANDIDATES",
    ]
    assert report["evaluated_candidate_instances"] == 1
    events = EvidenceStore(state).events()
    assert len([x for x in events if x["kind"] == "attempt"]) == 1
    generations = [x["payload"] for x in events if x["kind"] == "generation"]
    assert len(generations) == 2
    assert generations[-1]["duplicate_skipped"] == 1


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


def test_mixed_duplicate_generations_evaluate_only_unseen_semantics(tmp_path: Path) -> None:
    """Seed 8: periods 2,3; seed 9: periods 3,4. Evaluate three, not four."""
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    request = {
        **_request(generations=2),
        "count": 2,
        "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4]}],
    }
    started = service.start(request)
    jid = str(started["job_id"])
    for _ in range(150):
        time.sleep(0.2)
        current = service.status(jid)
        if current["status"] not in {"QUEUED", "RUNNING"}:
            break
    assert current["status"] == "COMPLETED", current
    report = service.report(jid)
    assert report["evaluated_candidate_instances"] == 3
    assert report["unique_candidate_count"] == 3
    assert report["total_skipped_duplicate_candidates"] == 1
    assert [item["candidate_count"] for item in report["generations"]] == [2, 1]
    assert [item["duplicate_skipped"] for item in report["generations"]] == [0, 1]
    events = [
        item["payload"]
        for item in EvidenceStore(tmp_path / "state").events()
        if item["kind"] == "attempt"
    ]
    assert [len(item["candidates"]) for item in events] == [2, 1]
    assert events[1]["execution"]["duplicate_skipped"] == 1


def test_random_collision_does_not_prematurely_stop_unexhausted_search(tmp_path: Path) -> None:
    """One duplicate random draw cannot prove that later draws are duplicates."""
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    started = service.start(
        {
            **_request(generations=4),
            "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3, 4]}],
        }
    )
    jid = str(started["job_id"])
    for _ in range(160):
        time.sleep(0.2)
        current = service.status(jid)
        if current["status"] not in {"QUEUED", "RUNNING"}:
            break
    assert current["status"] == "COMPLETED", current
    report = service.report(jid)
    assert report["requested_generations"] == 4
    assert report["completed_generations"] == 4
    assert report["stopped_early"] is False
    assert report["stop_reason"] is None
    assert report["skipped_duplicate_generations"] == 1
    assert report["evaluated_candidate_instances"] == 3


def test_fixed_grid_stops_when_all_candidates_were_already_evaluated(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    started = service.start(
        {
            **_request(generations=5),
            "method": "grid",
            "count": 2,
            "parameter_domains": [{"name": "indicators.fast.period", "values": [2, 3]}],
        }
    )
    jid = str(started["job_id"])
    for _ in range(160):
        time.sleep(0.2)
        current = service.status(jid)
        if current["status"] not in {"QUEUED", "RUNNING"}:
            break
    assert current["status"] == "COMPLETED", current
    report = service.report(jid)
    assert report["completed_generations"] == 2
    assert report["unexecuted_generations"] == 3
    assert report["stop_reason"] == "SEARCH_SPACE_EXHAUSTED"
    assert report["evaluated_candidate_instances"] == 2
    assert report["total_skipped_duplicate_candidates"] == 2


def test_legacy_batches_do_not_invent_zero_skipped_duplicate_counts(tmp_path: Path) -> None:
    import json

    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    with service._connect() as db:
        db.execute(
            "INSERT INTO batches (id,status,request_json,requested,completed,created) "
            "VALUES (?,?,?,?,?,?)",
            ("legacy", "COMPLETED", json.dumps({"method": "random", "count": 1}), 1, 1, 1),
        )
        db.execute(
            "INSERT INTO generation_history VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy",
                1,
                2.0,
                "random",
                1,
                "parent",
                "parent",
                "COMPLETED",
                json.dumps({"REJECT": 1}),
                1,
            ),
        )
    report = service.report("legacy")
    assert report["generations"][0]["duplicate_skipped"] is None
    assert report["total_skipped_duplicate_candidates"] is None
    assert report["evaluated_candidate_instances"] == 0


def test_mixed_mode_replans_from_failed_evidence_and_evaluates_new_hypothesis(
    tmp_path: Path,
) -> None:
    """Fixed-intent modes are unaffected; mixed mode actually evaluates new IR."""
    _write_inputs(tmp_path)
    service = ResearchBatchService(project_root=tmp_path, state_dir=tmp_path / "state")
    request = {
        **_request(generations=3),
        "intent": {
            **_request()["intent"],
            "mode": "mixed",
        },
    }
    started = service.start(request)
    for _ in range(160):
        time.sleep(0.2)
        status = service.status(str(started["job_id"]))
        if status["status"] not in {"QUEUED", "RUNNING"}:
            break
    assert status["status"] == "COMPLETED", status
    report = service.report(str(started["job_id"]))
    assert report["research_intent_mode"] == "mixed_evidence_guided_local"
    events = EvidenceStore(tmp_path / "state").events()
    generation_events = [event["payload"] for event in events if event["kind"] == "generation"]
    attempts = [event["payload"] for event in events if event["kind"] == "attempt"]
    assert attempts and all(
        attempt.get("verification") != "UNVERIFIED_EVALUATOR" for attempt in attempts
    )
    assert len(generation_events) >= 2
    assert generation_events[0].get("next_hypothesis") is not None
    plan = generation_events[0]["next_hypothesis"]
    assert plan["based_on_attempt_id"] == attempts[0]["attempt_id"]
    assert plan["causal_status"] == "HYPOTHESIS_NOT_VERIFIED_CAUSE"
    assert generation_events[1]["applied_hypothesis"] == plan
    first_ids = {c["semantic_strategy_hash"] for c in attempts[0]["candidates"]}
    second_ids = {c["semantic_strategy_hash"] for c in attempts[1]["candidates"]}
    assert second_ids - first_ids
    assert (
        attempts[1]["execution"]["parameter_domains"]
        != attempts[0]["execution"]["parameter_domains"]
        or attempts[1]["execution"]["parent_ir_hash"] != attempts[0]["execution"]["parent_ir_hash"]
        or plan["reason_code"].startswith("ENTRY_THRESHOLD_EXPERIMENT")
    )
    assert report["adaptive_replanned_generations"] >= 1
    assert report["evaluated_candidate_instances"] >= 2
    assert report["orders_enabled"] is False
    assert report["oos_approved"] is False
