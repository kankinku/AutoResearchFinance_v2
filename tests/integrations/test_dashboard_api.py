from __future__ import annotations

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


def test_dashboard_history_endpoints_return_commands_experiments_and_outbox(
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
    store.append_outbox_event(
        event_type="pipeline_started",
        payload={"run_id": "run-001"},
    )

    client = TestClient(create_dashboard_api(store=store, supervisor=supervisor))

    commands = client.get("/history/commands")
    experiments = client.get("/history/experiments")
    outbox = client.get("/history/outbox")

    assert commands.status_code == 200
    assert commands.json()[0]["command"] == "start_pipeline"
    assert experiments.status_code == 200
    assert experiments.json()[0]["candidate_revision"] == "candidate-001"
    assert outbox.status_code == 200
    assert outbox.json()[0]["event_type"] == "pipeline_started"
