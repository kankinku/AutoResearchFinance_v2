from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from .models import (
    AnalysisRecord,
    AutoresearchState,
    CommandSource,
    CommandRecord,
    ExperimentRecord,
    OutboxMessage,
    PipelineState,
    ProjectState,
    ProjectStatus,
    RunRecord,
    WorkerName,
)


class StateRepository(Protocol):
    def close(self) -> None: ...

    def get_status(self) -> ProjectStatus: ...

    def set_status(
        self,
        *,
        project_state: ProjectState | None = None,
        pipeline_state: PipelineState | None = None,
        autoresearch_state: AutoresearchState | None = None,
    ) -> ProjectStatus: ...

    def record_command(
        self,
        command: str,
        *,
        source: CommandSource,
        requested_by: str,
        requested_at: datetime | None = None,
        payload: Mapping[str, Any] | None = None,
        accepted: bool,
        project_state: ProjectState,
        pipeline_state: PipelineState,
        autoresearch_state: AutoresearchState,
        pending_command: str | None,
        message: str,
        run_id: str | None,
    ) -> CommandRecord: ...

    def list_commands(self, *, limit: int = 50) -> list[CommandRecord]: ...

    def record_run(
        self,
        *,
        run_id: str,
        state: str,
        created_at: datetime | None = None,
    ) -> RunRecord: ...

    def get_latest_run(self) -> RunRecord | None: ...

    def record_experiment(
        self,
        *,
        run_id: str,
        iteration: int,
        candidate_revision: str,
        baseline_revision: str,
        hypothesis: str,
        mutation_summary: str,
        backtest_metrics: Mapping[str, Any],
        decision: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> ExperimentRecord: ...

    def get_latest_experiment(self) -> ExperimentRecord | None: ...

    def list_experiments(self, *, limit: int = 50) -> list[ExperimentRecord]: ...

    def record_analysis(
        self,
        *,
        run_id: str,
        iteration: int,
        analysis_output: Mapping[str, Any],
        summary: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> AnalysisRecord: ...

    def get_latest_analysis(self) -> AnalysisRecord | None: ...

    def append_outbox_event(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        message_id: str | None = None,
        created_at: datetime | None = None,
    ) -> OutboxMessage: ...

    def list_pending_outbox(self) -> list[OutboxMessage]: ...

    def list_outbox(self, *, limit: int = 50) -> list[OutboxMessage]: ...

    def mark_outbox_sent(
        self,
        message_id: str,
        *,
        sent_at: datetime | None = None,
    ) -> OutboxMessage: ...

    def set_active_run(self, run_id: str | None) -> ProjectStatus: ...

    def set_current_stage(self, stage: str | None) -> ProjectStatus: ...

    def set_pending_command(self, command: str | None) -> ProjectStatus: ...

    def record_heartbeat(
        self,
        worker: WorkerName,
        timestamp: datetime | None = None,
    ) -> ProjectStatus: ...

    def clear_heartbeat(self, worker: WorkerName) -> ProjectStatus: ...

    def set_candidate_revision(self, revision: str | None) -> ProjectStatus: ...

    def set_baseline_revision(self, revision: str | None) -> ProjectStatus: ...

    def set_recovery_marker(self, marker: str | None) -> ProjectStatus: ...
