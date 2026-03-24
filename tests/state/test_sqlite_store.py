from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from finance_autoresearch.state.sqlite_store import SQLiteStateStore


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "state.db"


@pytest.fixture
def store(db_path: Path) -> SQLiteStateStore:
    repository = SQLiteStateStore(db_path=db_path, project_id="finance")
    yield repository
    repository.close()


def test_store_initializes_default_project_state(store: SQLiteStateStore) -> None:
    state = store.get_status()

    assert state.project_id == "finance"
    assert state.project_state == "idle"
    assert state.pipeline_state == "idle"
    assert state.autoresearch_state == "idle"
    assert state.active_run_id is None
    assert state.current_stage is None
    assert state.pending_command is None
    assert state.pipeline_heartbeat_at is None
    assert state.autoresearch_heartbeat_at is None
    assert state.candidate_revision is None
    assert state.baseline_revision is None
    assert state.recovery_marker is None


def test_store_creates_required_tables(db_path: Path) -> None:
    store = SQLiteStateStore(db_path=db_path, project_id="finance")
    store.close()

    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {
        "project_status",
        "command_history",
        "run_history",
        "experiment_history",
        "analysis_history",
        "outbox_messages",
    } <= table_names


def test_store_persists_bookkeeping_fields_across_reopen(db_path: Path) -> None:
    pipeline_heartbeat = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)
    autoresearch_heartbeat = datetime(2026, 3, 25, 0, 5, tzinfo=timezone.utc)

    first = SQLiteStateStore(db_path=db_path, project_id="finance")
    first.set_status(
        project_state="active",
        pipeline_state="success",
        autoresearch_state="running",
    )
    first.set_active_run("run-001")
    first.set_current_stage("run_backtest")
    first.set_pending_command("stop_autoresearch")
    first.record_heartbeat("pipeline", pipeline_heartbeat)
    first.record_heartbeat("autoresearch", autoresearch_heartbeat)
    first.set_candidate_revision("candidate-abc")
    first.set_baseline_revision("baseline-xyz")
    first.set_recovery_marker("iteration-07")
    first.close()

    reopened = SQLiteStateStore(db_path=db_path, project_id="finance")
    try:
        state = reopened.get_status()
    finally:
        reopened.close()

    assert state.project_state == "active"
    assert state.pipeline_state == "success"
    assert state.autoresearch_state == "running"
    assert state.active_run_id == "run-001"
    assert state.current_stage == "run_backtest"
    assert state.pending_command == "stop_autoresearch"
    assert state.pipeline_heartbeat_at == pipeline_heartbeat
    assert state.autoresearch_heartbeat_at == autoresearch_heartbeat
    assert state.candidate_revision == "candidate-abc"
    assert state.baseline_revision == "baseline-xyz"
    assert state.recovery_marker == "iteration-07"


def test_status_updates_do_not_clobber_other_fields_across_store_handles(
    db_path: Path,
) -> None:
    heartbeat = datetime(2026, 3, 25, 0, 20, tzinfo=timezone.utc)

    first = SQLiteStateStore(db_path=db_path, project_id="finance")
    second = SQLiteStateStore(db_path=db_path, project_id="finance")

    try:
        first.get_status()
        second.get_status()

        first.set_active_run("run-001")
        second.record_heartbeat("pipeline", heartbeat)

        final_state = first.get_status()
    finally:
        first.close()
        second.close()

    assert final_state.active_run_id == "run-001"
    assert final_state.pipeline_heartbeat_at == heartbeat


def test_command_history_persists_normalized_command_contract(db_path: Path) -> None:
    requested_at = datetime(2026, 3, 25, 0, 15, tzinfo=timezone.utc)

    first = SQLiteStateStore(db_path=db_path, project_id="finance")
    recorded = first.record_command(
        "start_pipeline",
        source="cli",
        requested_by="tester",
        requested_at=requested_at,
        payload={"force_refresh": True},
        accepted=True,
        project_state="active",
        pipeline_state="running",
        autoresearch_state="idle",
        pending_command=None,
        message="pipeline started",
        run_id="run-001",
    )
    first.close()

    reopened = SQLiteStateStore(db_path=db_path, project_id="finance")
    try:
        commands = reopened.list_commands()
    finally:
        reopened.close()

    assert [command.id for command in commands] == [recorded.id]
    assert commands[0].command == "start_pipeline"
    assert commands[0].source == "cli"
    assert commands[0].requested_by == "tester"
    assert commands[0].requested_at == requested_at
    assert commands[0].payload == {"force_refresh": True}
    assert commands[0].accepted is True
    assert commands[0].project_state == "active"
    assert commands[0].pipeline_state == "running"
    assert commands[0].autoresearch_state == "idle"
    assert commands[0].pending_command is None
    assert commands[0].message == "pipeline started"
    assert commands[0].run_id == "run-001"


def test_store_records_latest_experiment_and_analysis_results(db_path: Path) -> None:
    experiment_created = datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc)
    analysis_created = datetime(2026, 3, 25, 1, 5, tzinfo=timezone.utc)
    analysis_output = {
        "strengths": ["bull trend capture improved"],
        "weaknesses": ["bear drawdown remains elevated"],
        "coverage_gaps": ["needs choppy-market filter"],
        "regime_observations": ["bull regime improved more than bear regime"],
        "next_hypothesis_hints": ["tighten exits in bear regime"],
        "summary": "Bull regime improved but bear drawdown remains weak.",
    }

    first = SQLiteStateStore(db_path=db_path, project_id="finance")
    experiment = first.record_experiment(
        run_id="run-001",
        iteration=7,
        candidate_revision="candidate-abc",
        baseline_revision="baseline-xyz",
        hypothesis="Use RSI to gate long entries in bull regimes.",
        mutation_summary="Added bull/bear branches with RSI threshold filter.",
        backtest_metrics={"score": 1.42, "guardrails_passed": True},
        decision="keep",
        created_at=experiment_created,
        updated_at=experiment_created,
    )
    analysis = first.record_analysis(
        run_id="run-001",
        iteration=7,
        analysis_output=analysis_output,
        summary=analysis_output["summary"],
        created_at=analysis_created,
        updated_at=analysis_created,
    )
    first.close()

    reopened = SQLiteStateStore(db_path=db_path, project_id="finance")
    try:
        latest_experiment = reopened.get_latest_experiment()
        latest_analysis = reopened.get_latest_analysis()
    finally:
        reopened.close()

    assert latest_experiment is not None
    assert latest_experiment.id == experiment.id
    assert latest_experiment.run_id == "run-001"
    assert latest_experiment.iteration == 7
    assert latest_experiment.candidate_revision == "candidate-abc"
    assert latest_experiment.baseline_revision == "baseline-xyz"
    assert latest_experiment.hypothesis == "Use RSI to gate long entries in bull regimes."
    assert latest_experiment.mutation_summary == "Added bull/bear branches with RSI threshold filter."
    assert latest_experiment.backtest_metrics == {"score": 1.42, "guardrails_passed": True}
    assert latest_experiment.decision == "keep"
    assert latest_experiment.created_at == experiment_created
    assert latest_experiment.updated_at == experiment_created

    assert latest_analysis is not None
    assert latest_analysis.id == analysis.id
    assert latest_analysis.run_id == "run-001"
    assert latest_analysis.iteration == 7
    assert latest_analysis.analysis_output == analysis_output
    assert latest_analysis.summary == analysis_output["summary"]
    assert latest_analysis.created_at == analysis_created
    assert latest_analysis.updated_at == analysis_created


def test_store_tracks_run_history_and_latest_records_by_timestamp(db_path: Path) -> None:
    older_timestamp = datetime(2026, 3, 25, 0, 30, tzinfo=timezone.utc)
    newer_timestamp = datetime(2026, 3, 25, 0, 45, tzinfo=timezone.utc)

    first = SQLiteStateStore(db_path=db_path, project_id="finance")
    first.record_run(
        run_id="run-newer",
        state="success",
        created_at=newer_timestamp,
    )
    first.record_run(
        run_id="run-older",
        state="failed",
        created_at=older_timestamp,
    )
    first.record_experiment(
        run_id="run-newer",
        iteration=2,
        candidate_revision="candidate-newer",
        baseline_revision="baseline-newer",
        hypothesis="Prefer the newer experiment.",
        mutation_summary="Newer experiment inserted first.",
        backtest_metrics={"score": 1.0},
        decision="keep",
        created_at=newer_timestamp,
        updated_at=newer_timestamp,
    )
    first.record_experiment(
        run_id="run-older",
        iteration=1,
        candidate_revision="candidate-older",
        baseline_revision="baseline-older",
        hypothesis="Older experiment inserted second.",
        mutation_summary="Older experiment inserted after the newer one.",
        backtest_metrics={"score": 0.5},
        decision="rollback",
        created_at=older_timestamp,
        updated_at=older_timestamp,
    )
    first.record_analysis(
        run_id="run-newer",
        iteration=2,
        analysis_output={
            "strengths": ["newer analysis"],
            "weaknesses": [],
            "coverage_gaps": [],
            "regime_observations": [],
            "next_hypothesis_hints": [],
            "summary": "newer analysis",
        },
        summary="newer analysis",
        created_at=newer_timestamp,
        updated_at=newer_timestamp,
    )
    first.record_analysis(
        run_id="run-older",
        iteration=1,
        analysis_output={
            "strengths": ["older analysis"],
            "weaknesses": [],
            "coverage_gaps": [],
            "regime_observations": [],
            "next_hypothesis_hints": [],
            "summary": "older analysis",
        },
        summary="older analysis",
        created_at=older_timestamp,
        updated_at=older_timestamp,
    )
    first.close()

    reopened = SQLiteStateStore(db_path=db_path, project_id="finance")
    try:
        latest_run = reopened.get_latest_run()
        latest_experiment = reopened.get_latest_experiment()
        latest_analysis = reopened.get_latest_analysis()
    finally:
        reopened.close()

    assert latest_run is not None
    assert latest_run.run_id == "run-newer"
    assert latest_run.state == "success"
    assert latest_run.created_at == newer_timestamp

    assert latest_experiment is not None
    assert latest_experiment.run_id == "run-newer"
    assert latest_experiment.created_at == newer_timestamp

    assert latest_analysis is not None
    assert latest_analysis.run_id == "run-newer"
    assert latest_analysis.created_at == newer_timestamp


def test_run_history_is_scoped_per_project(db_path: Path) -> None:
    finance_timestamp = datetime(2026, 3, 25, 2, 0, tzinfo=timezone.utc)
    sandbox_timestamp = datetime(2026, 3, 25, 2, 5, tzinfo=timezone.utc)

    finance_store = SQLiteStateStore(db_path=db_path, project_id="finance")
    sandbox_store = SQLiteStateStore(db_path=db_path, project_id="sandbox")

    try:
        finance_store.record_run(
            run_id="run-001",
            state="success",
            created_at=finance_timestamp,
        )
        sandbox_store.record_run(
            run_id="run-001",
            state="failed",
            created_at=sandbox_timestamp,
        )

        finance_run = finance_store.get_latest_run()
        sandbox_run = sandbox_store.get_latest_run()
    finally:
        finance_store.close()
        sandbox_store.close()

    assert finance_run is not None
    assert finance_run.project_id == "finance"
    assert finance_run.state == "success"
    assert finance_run.created_at == finance_timestamp

    assert sandbox_run is not None
    assert sandbox_run.project_id == "sandbox"
    assert sandbox_run.state == "failed"
    assert sandbox_run.created_at == sandbox_timestamp


def test_store_normalizes_write_timestamps_to_utc(db_path: Path) -> None:
    kst = timezone(timedelta(hours=9))
    local_timestamp = datetime(2026, 3, 25, 9, 0, tzinfo=kst)
    expected_utc = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)

    def assert_is_utc_timestamp(value: datetime) -> None:
        assert value.isoformat() == expected_utc.isoformat()
        assert value.tzinfo == timezone.utc

    first = SQLiteStateStore(db_path=db_path, project_id="finance")
    command = first.record_command(
        "start_pipeline",
        source="cli",
        requested_by="tester",
        requested_at=local_timestamp,
        payload={"force_refresh": True},
        accepted=True,
        project_state="active",
        pipeline_state="running",
        autoresearch_state="idle",
        pending_command=None,
        message="pipeline started",
        run_id="run-001",
    )
    run = first.record_run(
        run_id="run-001",
        state="running",
        created_at=local_timestamp,
    )
    experiment = first.record_experiment(
        run_id="run-001",
        iteration=1,
        candidate_revision="candidate-utc",
        baseline_revision="baseline-utc",
        hypothesis="Normalize timestamps to UTC.",
        mutation_summary="No-op for timestamp normalization test.",
        backtest_metrics={"score": 1.0},
        decision="keep",
        created_at=local_timestamp,
        updated_at=local_timestamp,
    )
    analysis = first.record_analysis(
        run_id="run-001",
        iteration=1,
        analysis_output={
            "strengths": ["consistent timestamps"],
            "weaknesses": [],
            "coverage_gaps": [],
            "regime_observations": [],
            "next_hypothesis_hints": [],
            "summary": "timestamps normalized",
        },
        summary="timestamps normalized",
        created_at=local_timestamp,
        updated_at=local_timestamp,
    )
    status = first.record_heartbeat("pipeline", local_timestamp)
    event = first.append_outbox_event(
        event_type="pipeline_started",
        payload={"run_id": "run-001"},
        created_at=local_timestamp,
    )
    sent_event = first.mark_outbox_sent(event.id, sent_at=local_timestamp)
    first.close()

    reopened = SQLiteStateStore(db_path=db_path, project_id="finance")
    try:
        persisted_status = reopened.get_status()
        persisted_command = reopened.list_commands(limit=1)[0]
        persisted_run = reopened.get_latest_run()
        persisted_experiment = reopened.get_latest_experiment()
        persisted_analysis = reopened.get_latest_analysis()
        pending_outbox = reopened.list_pending_outbox()
    finally:
        reopened.close()

    assert_is_utc_timestamp(command.requested_at)
    assert_is_utc_timestamp(run.created_at)
    assert_is_utc_timestamp(experiment.created_at)
    assert_is_utc_timestamp(experiment.updated_at)
    assert_is_utc_timestamp(analysis.created_at)
    assert_is_utc_timestamp(analysis.updated_at)
    assert status.pipeline_heartbeat_at is not None
    assert_is_utc_timestamp(status.pipeline_heartbeat_at)
    assert_is_utc_timestamp(event.created_at)
    assert sent_event.sent_at is not None
    assert_is_utc_timestamp(sent_event.created_at)
    assert_is_utc_timestamp(sent_event.sent_at)

    assert persisted_status.pipeline_heartbeat_at is not None
    assert_is_utc_timestamp(persisted_status.pipeline_heartbeat_at)
    assert_is_utc_timestamp(persisted_command.requested_at)
    assert persisted_run is not None
    assert_is_utc_timestamp(persisted_run.created_at)
    assert persisted_experiment is not None
    assert_is_utc_timestamp(persisted_experiment.created_at)
    assert_is_utc_timestamp(persisted_experiment.updated_at)
    assert persisted_analysis is not None
    assert_is_utc_timestamp(persisted_analysis.created_at)
    assert_is_utc_timestamp(persisted_analysis.updated_at)
    assert pending_outbox == []


def test_outbox_events_can_be_appended_and_marked_sent(db_path: Path) -> None:
    created_at = datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc)
    sent_at = datetime(2026, 3, 25, 1, 10, tzinfo=timezone.utc)

    first = SQLiteStateStore(db_path=db_path, project_id="finance")
    event = first.append_outbox_event(
        event_type="pipeline_recovered_stale",
        payload={"run_id": "run-001"},
        created_at=created_at,
    )
    first.close()

    reopened = SQLiteStateStore(db_path=db_path, project_id="finance")
    try:
        pending = reopened.list_pending_outbox()
        sent_event = reopened.mark_outbox_sent(event.id, sent_at=sent_at)
        still_pending = reopened.list_pending_outbox()
    finally:
        reopened.close()

    assert [message.id for message in pending] == [event.id]
    assert pending[0].event_type == "pipeline_recovered_stale"
    assert pending[0].payload == {"run_id": "run-001"}
    assert pending[0].created_at == created_at
    assert pending[0].sent_at is None
    assert sent_event.id == event.id
    assert sent_event.sent_at == sent_at
    assert still_pending == []
