from __future__ import annotations

from fastapi import FastAPI

from finance_autoresearch.state.models import (
    AnalysisRecord,
    CommandRecord,
    ExperimentRecord,
    OutboxMessage,
    serialize_datetime,
)
from finance_autoresearch.state.repository import StateRepository
from finance_autoresearch.supervisor.service import SupervisorService


def create_dashboard_api(
    *,
    store: StateRepository,
    supervisor: SupervisorService | None = None,
) -> FastAPI:
    app = FastAPI(title="finance-autoresearch-dashboard")

    @app.get("/status")
    def status() -> dict[str, object]:
        current = store.get_status()
        return {
            "project_id": current.project_id,
            "project_state": current.project_state,
            "pipeline_state": current.pipeline_state,
            "autoresearch_state": current.autoresearch_state,
            "run_id": current.active_run_id,
            "current_stage": current.current_stage,
            "pending_command": current.pending_command,
            "candidate_revision": current.candidate_revision,
            "baseline_revision": current.baseline_revision,
            "pipeline_heartbeat_at": serialize_datetime(current.pipeline_heartbeat_at),
            "autoresearch_heartbeat_at": serialize_datetime(
                current.autoresearch_heartbeat_at
            ),
        }

    @app.get("/history/commands")
    def history_commands(limit: int = 50) -> list[dict[str, object]]:
        return [_serialize_command(record) for record in store.list_commands(limit=limit)]

    @app.get("/history/experiments")
    def history_experiments(limit: int = 50) -> list[dict[str, object]]:
        return [
            _serialize_experiment(record) for record in store.list_experiments(limit=limit)
        ]

    @app.get("/history/outbox")
    def history_outbox(limit: int = 50) -> list[dict[str, object]]:
        return [_serialize_outbox(record) for record in store.list_outbox(limit=limit)]

    return app


def _serialize_command(record: CommandRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "command": record.command,
        "source": record.source,
        "requested_by": record.requested_by,
        "requested_at": serialize_datetime(record.requested_at),
        "payload": record.payload,
        "accepted": record.accepted,
        "project_state": record.project_state,
        "pipeline_state": record.pipeline_state,
        "autoresearch_state": record.autoresearch_state,
        "pending_command": record.pending_command,
        "message": record.message,
        "run_id": record.run_id,
    }


def _serialize_experiment(record: ExperimentRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "candidate_revision": record.candidate_revision,
        "baseline_revision": record.baseline_revision,
        "hypothesis": record.hypothesis,
        "mutation_summary": record.mutation_summary,
        "backtest_metrics": record.backtest_metrics,
        "decision": record.decision,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_analysis(record: AnalysisRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "analysis_output": record.analysis_output,
        "summary": record.summary,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_outbox(record: OutboxMessage) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "event_type": record.event_type,
        "payload": record.payload,
        "created_at": serialize_datetime(record.created_at),
        "sent_at": serialize_datetime(record.sent_at),
    }
