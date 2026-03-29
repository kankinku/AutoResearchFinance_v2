from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

ProjectState = Literal["idle", "active", "paused", "degraded"]
PipelineState = Literal["idle", "running", "success", "failed"]
AutoresearchState = Literal["idle", "running", "paused", "success", "failed", "stale"]
WorkerName = Literal["pipeline", "autoresearch"]
CommandSource = Literal["cli", "telegram_control", "openclaw", "dashboard"]


@dataclass(slots=True, frozen=True)
class ProjectStatus:
    project_id: str
    project_state: ProjectState
    pipeline_state: PipelineState
    autoresearch_state: AutoresearchState
    active_run_id: str | None = None
    current_stage: str | None = None
    pending_command: str | None = None
    pipeline_heartbeat_at: datetime | None = None
    autoresearch_heartbeat_at: datetime | None = None
    candidate_revision: str | None = None
    baseline_revision: str | None = None
    recovery_marker: str | None = None


@dataclass(slots=True, frozen=True)
class CommandRecord:
    id: int
    project_id: str
    command: str
    source: CommandSource
    requested_by: str
    requested_at: datetime
    payload: dict[str, Any]
    accepted: bool
    project_state: ProjectState
    pipeline_state: PipelineState
    autoresearch_state: AutoresearchState
    pending_command: str | None
    message: str
    run_id: str | None


@dataclass(slots=True, frozen=True)
class RunRecord:
    run_id: str
    project_id: str
    state: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class IterationHistoryRecord:
    run_id: str
    iteration: int
    run: RunRecord | None
    decision: str | None
    experiment: ExperimentRecord | None
    analysis: AnalysisRecord | None
    research_plan: ResearchPlanRecord | None
    lesson: LessonRecord | None
    last_updated_at: datetime | None = None
    trial: TrialRecord | None = None
    falsification: FalsificationRecord | None = None
    lesson_graph: LessonGraphRecord | None = None
    family_memory: FamilyMemoryRecord | None = None
    frontier: tuple[CandidateFrontierRecord, ...] = ()
    linked_brain_notes: tuple[BrainNoteRecord, ...] = ()


@dataclass(slots=True, frozen=True)
class ExperimentRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    candidate_revision: str
    baseline_revision: str
    hypothesis: str
    mutation_summary: str
    backtest_metrics: dict[str, Any]
    decision: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class AnalysisRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    analysis_output: dict[str, Any]
    summary: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class ResearchPlanRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    hypothesis: str
    summary: str
    plan_output: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class KnowledgeRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    source_path: str
    title: str
    excerpt: str
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(slots=True, frozen=True)
class LessonRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    decision: str
    summary: str
    lesson_output: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class BrainNoteRecord:
    id: int
    project_id: str
    note_type: str
    path: str
    title: str
    generated: bool
    run_id: str | None
    iteration: int | None
    revision: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class TrialRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    family: str
    artifact_kind: str
    candidate_revision: str
    baseline_revision: str
    compile_status: str
    falsification_pass: bool
    decision: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class FalsificationRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    candidate_revision: str
    passed: bool
    checks: dict[str, Any]
    summary: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class LessonGraphRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    decision: str
    thesis: str
    mutation_delta: str
    observed_outcome: str
    failure_mode: str
    next_action: str
    confidence: str
    novelty_score: float
    knowledge_source_ids: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class FamilyMemoryRecord:
    id: int
    project_id: str
    family: str
    symbol_scope: str
    timeframe_scope: str
    regime_scope: str
    outcome: str
    linked_run_id: str
    linked_iteration: int
    novelty_score: float
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class CandidateFrontierRecord:
    id: int
    project_id: str
    run_id: str
    iteration: int
    candidate_id: str
    rank: int
    promoted: bool
    prescreen_reason: str
    prescreen_score: float
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class OutboxMessage:
    id: str
    project_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    sent_at: datetime | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return ensure_utc(value).isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return ensure_utc(datetime.fromisoformat(value))
