from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from .models import (
    AnalysisRecord,
    AutoresearchState,
    BrainNoteRecord,
    CandidateFrontierRecord,
    CommandSource,
    CommandRecord,
    ExperimentRecord,
    FamilyMemoryRecord,
    FalsificationRecord,
    IterationHistoryRecord,
    KnowledgeRecord,
    LessonRecord,
    LessonGraphRecord,
    OutboxMessage,
    PipelineState,
    ProjectState,
    ProjectStatus,
    ResearchPlanRecord,
    RunRecord,
    TrialRecord,
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
        updated_at: datetime | None = None,
    ) -> RunRecord: ...

    def get_latest_run(self) -> RunRecord | None: ...

    def list_runs(self, *, limit: int = 50) -> list[RunRecord]: ...

    def list_iteration_history(
        self,
        *,
        limit: int = 50,
    ) -> list[IterationHistoryRecord]: ...

    def get_iteration_history_entry(
        self,
        *,
        run_id: str,
        iteration: int,
    ) -> IterationHistoryRecord | None: ...

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

    def list_analyses(self, *, limit: int = 50) -> list[AnalysisRecord]: ...

    def record_research_plan(
        self,
        *,
        run_id: str,
        iteration: int,
        hypothesis: str,
        summary: str,
        plan_output: Mapping[str, Any],
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> ResearchPlanRecord: ...

    def get_latest_research_plan(self) -> ResearchPlanRecord | None: ...

    def list_research_plans(self, *, limit: int = 50) -> list[ResearchPlanRecord]: ...

    def record_knowledge(
        self,
        *,
        run_id: str,
        iteration: int,
        source_path: str,
        title: str,
        excerpt: str,
        metadata: Mapping[str, Any],
        created_at: datetime | None = None,
    ) -> KnowledgeRecord: ...

    def list_knowledge(self, *, limit: int = 50) -> list[KnowledgeRecord]: ...

    def record_lesson(
        self,
        *,
        run_id: str,
        iteration: int,
        decision: str,
        summary: str,
        lesson_output: Mapping[str, Any],
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> LessonRecord: ...

    def get_latest_lesson(self) -> LessonRecord | None: ...

    def list_lessons(self, *, limit: int = 50) -> list[LessonRecord]: ...

    def record_brain_note(
        self,
        *,
        note_type: str,
        path: str,
        title: str,
        generated: bool,
        run_id: str | None = None,
        iteration: int | None = None,
        revision: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> BrainNoteRecord: ...

    def list_brain_notes(
        self,
        *,
        limit: int = 50,
        note_type: str | None = None,
    ) -> list[BrainNoteRecord]: ...

    def list_brain_maps(self, *, limit: int = 50) -> list[BrainNoteRecord]: ...

    def record_trial(
        self,
        *,
        run_id: str,
        iteration: int,
        family: str,
        artifact_kind: str,
        candidate_revision: str,
        baseline_revision: str,
        compile_status: str,
        falsification_pass: bool,
        decision: str,
        metadata: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> TrialRecord: ...

    def list_trials(self, *, limit: int = 50) -> list[TrialRecord]: ...

    def record_falsification(
        self,
        *,
        run_id: str,
        iteration: int,
        candidate_revision: str,
        passed: bool,
        checks: Mapping[str, Any],
        summary: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> FalsificationRecord: ...

    def list_falsifications(self, *, limit: int = 50) -> list[FalsificationRecord]: ...

    def record_lesson_graph(
        self,
        *,
        run_id: str,
        iteration: int,
        decision: str,
        thesis: str,
        mutation_delta: str,
        observed_outcome: str,
        failure_mode: str,
        next_action: str,
        confidence: str,
        novelty_score: float,
        knowledge_source_ids: tuple[str, ...],
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> LessonGraphRecord: ...

    def list_lesson_graph(self, *, limit: int = 50) -> list[LessonGraphRecord]: ...

    def record_family_memory(
        self,
        *,
        family: str,
        symbol_scope: str,
        timeframe_scope: str,
        regime_scope: str,
        outcome: str,
        linked_run_id: str,
        linked_iteration: int,
        novelty_score: float,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> FamilyMemoryRecord: ...

    def list_family_memory(self, *, limit: int = 50) -> list[FamilyMemoryRecord]: ...

    def record_candidate_frontier(
        self,
        *,
        run_id: str,
        iteration: int,
        candidate_id: str,
        rank: int,
        promoted: bool,
        prescreen_reason: str,
        prescreen_score: float,
        metadata: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> CandidateFrontierRecord: ...

    def list_candidate_frontier(
        self,
        *,
        limit: int = 50,
    ) -> list[CandidateFrontierRecord]: ...

    def append_outbox_event(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        message_id: str | None = None,
        created_at: datetime | None = None,
    ) -> OutboxMessage: ...

    def list_pending_outbox(
        self,
        *,
        event_type_prefix: str | None = None,
        exclude_event_type_prefix: str | None = None,
    ) -> list[OutboxMessage]: ...

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
