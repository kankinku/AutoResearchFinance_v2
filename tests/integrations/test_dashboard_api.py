from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from finance_autoresearch.state.sqlite_store import SQLiteStateStore
from finance_autoresearch.supervisor.service import SupervisorService


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStateStore:
    repository = SQLiteStateStore(db_path=tmp_path / "state.db", project_id="finance")
    yield repository
    repository.close()


def test_dashboard_status_matches_supervisor_status(store: SQLiteStateStore) -> None:
    from finance_autoresearch.integrations.cli import dispatch_command
    from finance_autoresearch.integrations.dashboard_api import create_dashboard_api

    supervisor = SupervisorService(
        state_store=store,
        seed_validator=lambda _project_id: (True, "seed baseline validated"),
        run_id_factory=lambda: "run-001",
    )
    cli_status = dispatch_command(
        supervisor=supervisor,
        command="status",
        source="cli",
        requested_by="cli-user",
        project_id="finance",
    )
    client = TestClient(create_dashboard_api(store=store, supervisor=supervisor))

    response = client.get("/status")

    assert response.status_code == 200
    assert response.json()["project_state"] == cli_status["project_state"]
    assert response.json()["pipeline_state"] == cli_status["pipeline_state"]
    assert response.json()["autoresearch_state"] == cli_status["autoresearch_state"]
    assert response.json()["run_id"] == cli_status["run_id"]


def test_dashboard_history_endpoints_return_commands_experiments_and_research_artifacts(
    store: SQLiteStateStore,
) -> None:
    from finance_autoresearch.integrations.dashboard_api import create_dashboard_api

    supervisor = SupervisorService(
        state_store=store,
        seed_validator=lambda _project_id: (True, "seed baseline validated"),
        run_id_factory=lambda: "run-001",
    )
    supervisor.handle(
        {
            "command": "start_pipeline",
            "project_id": "finance",
            "source": "dashboard",
            "requested_by": "dashboard-user",
            "requested_at": "2026-03-25T00:00:00+00:00",
            "payload": {},
        }
    )
    store.record_experiment(
        run_id="run-001",
        iteration=1,
        candidate_revision="candidate-001",
        baseline_revision="baseline-001",
        hypothesis="test hypothesis",
        mutation_summary="test mutation",
        backtest_metrics={"score": 1.0},
        decision="keep",
    )
    store.record_research_plan(
        run_id="run-001",
        iteration=1,
        hypothesis="test plan",
        summary="test summary",
        plan_output={"experiment_type": "simplify_filters"},
    )
    store.record_analysis(
        run_id="run-001",
        iteration=1,
        analysis_output={
            "strengths": ["bull improved"],
            "weaknesses": ["bear weak"],
            "coverage_gaps": ["needs another exit check"],
            "regime_observations": ["bull outperformed bear"],
            "next_hypothesis_hints": ["tighten exits"],
            "summary": "analysis summary",
        },
        summary="analysis summary",
    )
    store.record_run(run_id="run-001", state="success")
    store.record_knowledge(
        run_id="run-001",
        iteration=1,
        source_path="knowledge/indicators/rsi.md",
        title="RSI Notes",
        excerpt="RSI notes excerpt",
        metadata={"tags": ["knowledge-pack", "indicators", "rsi"]},
    )
    store.record_lesson(
        run_id="run-001",
        iteration=1,
        decision="keep",
        summary="lesson summary",
        lesson_output={"lessons": [{"statement": "Preserve exposure."}]},
    )
    store.record_brain_note(
        note_type="iteration",
        path="01 Iterations/run-001-1.md",
        title="Iteration 1",
        generated=True,
        run_id="run-001",
        iteration=1,
        revision="candidate-001",
        metadata={"tags": ["brain", "iteration"]},
    )
    store.record_brain_note(
        note_type="map",
        path="90 Maps/Active Experiments.md",
        title="Active Experiments",
        generated=True,
        metadata={"sections": ["Experiment"]},
    )
    store.record_trial(
        run_id="run-001",
        iteration=1,
        family="simplify_filters",
        artifact_kind="strategy_replacement",
        candidate_revision="candidate-001",
        baseline_revision="baseline-001",
        compile_status="compiled",
        falsification_pass=True,
        decision="keep",
        metadata={"shadow_match": True},
    )
    store.record_falsification(
        run_id="run-001",
        iteration=1,
        candidate_revision="candidate-001",
        passed=True,
        checks={"validation_stability": {"passed": True, "message": "ok"}},
        summary="all checks passed",
    )
    store.record_lesson_graph(
        run_id="run-001",
        iteration=1,
        decision="keep",
        thesis="simplify one filter",
        mutation_delta="removed one guard",
        observed_outcome="keep",
        failure_mode="",
        next_action="stress the weakest slice",
        confidence="medium",
        novelty_score=0.6,
        knowledge_source_ids=("knowledge/indicators/rsi.md",),
    )
    store.record_family_memory(
        family="simplify_filters",
        symbol_scope="all",
        timeframe_scope="mixed",
        regime_scope="mixed",
        outcome="keep",
        linked_run_id="run-001",
        linked_iteration=1,
        novelty_score=0.6,
    )
    store.record_candidate_frontier(
        run_id="run-001",
        iteration=1,
        candidate_id="candidate-001-a",
        rank=1,
        promoted=True,
        prescreen_reason="passed",
        prescreen_score=0.8,
        metadata={"artifact_kind": "strategy_replacement"},
    )
    store.append_outbox_event(
        event_type="pipeline_started",
        payload={"run_id": "run-001"},
    )

    client = TestClient(create_dashboard_api(store=store, supervisor=supervisor))

    commands = client.get("/history/commands")
    experiments = client.get("/history/experiments")
    analyses = client.get("/history/analysis")
    runs = client.get("/history/runs")
    research_plans = client.get("/history/research-plans")
    knowledge = client.get("/history/knowledge")
    lessons = client.get("/history/lessons")
    iterations = client.get("/history/iterations")
    outbox = client.get("/history/outbox")
    brain_notes = client.get("/history/brain-notes")
    brain_maps = client.get("/history/brain-maps")
    trials = client.get("/history/trials")
    falsification = client.get("/history/falsification")
    frontier = client.get("/history/frontier")
    lesson_graph = client.get("/history/lesson-graph")
    family_memory = client.get("/history/family-memory")
    filtered_iterations = client.get(
        "/history/iterations",
        params={"run_id": "run-001", "iteration": 1, "limit": 5},
    )
    filtered_falsification = client.get(
        "/history/falsification",
        params={"run_id": "run-001", "iteration": 1, "limit": 5},
    )

    assert commands.status_code == 200
    assert commands.json()[0]["command"] == "start_pipeline"
    assert experiments.status_code == 200
    assert experiments.json()[0]["candidate_revision"] == "candidate-001"
    assert analyses.status_code == 200
    assert analyses.json()[0]["summary"] == "analysis summary"
    assert runs.status_code == 200
    assert runs.json()[0]["run_id"] == "run-001"
    assert research_plans.status_code == 200
    assert research_plans.json()[0]["hypothesis"] == "test plan"
    assert knowledge.status_code == 200
    assert knowledge.json()[0]["source_path"] == "knowledge/indicators/rsi.md"
    assert lessons.status_code == 200
    assert lessons.json()[0]["summary"] == "lesson summary"
    assert iterations.status_code == 200
    assert iterations.json()[0]["run_id"] == "run-001"
    assert iterations.json()[0]["decision"] == "keep"
    assert iterations.json()[0]["analysis"]["summary"] == "analysis summary"
    assert iterations.json()[0]["research_plan"]["plan_output"]["experiment_type"] == "simplify_filters"
    assert outbox.status_code == 200
    assert outbox.json()[0]["event_type"] == "pipeline_started"
    assert brain_notes.status_code == 200
    assert brain_notes.json()[0]["path"] == "90 Maps/Active Experiments.md" or brain_notes.json()[0]["path"] == "01 Iterations/run-001-1.md"
    assert brain_maps.status_code == 200
    assert brain_maps.json()[0]["path"] == "90 Maps/Active Experiments.md"
    assert trials.status_code == 200
    assert trials.json()[0]["artifact_kind"] == "strategy_replacement"
    assert falsification.status_code == 200
    assert falsification.json()[0]["passed"] is True
    assert frontier.status_code == 200
    assert frontier.json()[0]["candidate_id"] == "candidate-001-a"
    assert lesson_graph.status_code == 200
    assert lesson_graph.json()[0]["thesis"] == "simplify one filter"
    assert family_memory.status_code == 200
    assert family_memory.json()[0]["family"] == "simplify_filters"
    assert filtered_iterations.status_code == 200
    assert filtered_iterations.json()[0]["run_id"] == "run-001"
    assert filtered_iterations.json()[0]["iteration"] == 1
    assert filtered_falsification.status_code == 200
    assert filtered_falsification.json()[0]["candidate_revision"] == "candidate-001"
    assert iterations.json()[0]["trial"]["artifact_kind"] == "strategy_replacement"
    assert iterations.json()[0]["falsification"]["passed"] is True
    assert iterations.json()[0]["lesson_graph"]["observed_outcome"] == "keep"
    assert iterations.json()[0]["family_memory"]["family"] == "simplify_filters"
    assert iterations.json()[0]["frontier"][0]["candidate_id"] == "candidate-001-a"


def test_dashboard_iteration_history_anchors_on_experiments_instead_of_limited_side_joins(
    store: SQLiteStateStore,
) -> None:
    from finance_autoresearch.integrations.dashboard_api import create_dashboard_api

    anchor_time = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)
    later_time = anchor_time + timedelta(minutes=5)
    store.record_run(
        run_id="run-anchor",
        state="success",
        created_at=anchor_time,
        updated_at=later_time,
    )
    store.record_experiment(
        run_id="run-anchor",
        iteration=1,
        candidate_revision="candidate-anchor",
        baseline_revision="baseline-anchor",
        hypothesis="anchor",
        mutation_summary="anchor",
        backtest_metrics={"score": 1.1},
        decision="keep",
        created_at=anchor_time,
        updated_at=anchor_time,
    )
    store.record_analysis(
        run_id="run-anchor",
        iteration=1,
        analysis_output={
            "strengths": ["anchor strength"],
            "weaknesses": [],
            "coverage_gaps": [],
            "regime_observations": [],
            "next_hypothesis_hints": [],
            "summary": "anchor analysis",
        },
        summary="anchor analysis",
        created_at=anchor_time,
        updated_at=anchor_time,
    )
    store.record_research_plan(
        run_id="run-anchor",
        iteration=1,
        hypothesis="anchor plan",
        summary="anchor plan",
        plan_output={"experiment_type": "simplify_filters"},
        created_at=anchor_time,
        updated_at=anchor_time,
    )
    store.record_lesson(
        run_id="run-anchor",
        iteration=1,
        decision="keep",
        summary="anchor lesson",
        lesson_output={"lessons": [{"statement": "anchor lesson"}]},
        created_at=anchor_time,
        updated_at=anchor_time,
    )

    store.record_analysis(
        run_id="run-other",
        iteration=99,
        analysis_output={
            "strengths": ["other"],
            "weaknesses": [],
            "coverage_gaps": [],
            "regime_observations": [],
            "next_hypothesis_hints": [],
            "summary": "other analysis",
        },
        summary="other analysis",
        created_at=later_time,
        updated_at=later_time,
    )
    store.record_research_plan(
        run_id="run-other",
        iteration=99,
        hypothesis="other",
        summary="other",
        plan_output={"experiment_type": "tighten_risk"},
        created_at=later_time,
        updated_at=later_time,
    )
    store.record_lesson(
        run_id="run-other",
        iteration=99,
        decision="rollback",
        summary="other lesson",
        lesson_output={"lessons": [{"statement": "other lesson"}]},
        created_at=later_time,
        updated_at=later_time,
    )

    client = TestClient(create_dashboard_api(store=store))

    response = client.get("/history/iterations", params={"limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["run_id"] == "run-anchor"
    assert payload[0]["analysis"]["summary"] == "anchor analysis"
    assert payload[0]["research_plan"]["summary"] == "anchor plan"
    assert payload[0]["lesson"]["summary"] == "anchor lesson"
