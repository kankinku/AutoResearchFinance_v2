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
