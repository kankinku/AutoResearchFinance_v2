from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeComponentSnapshot(RuntimeModel):
    id: str
    status: str = "UNKNOWN"
    alive: bool | None = None
    pid: int | None = None
    active_jobs: int = 0
    queued_jobs: int = 0
    mode: str | None = None


class ManagedSystemSnapshot(RuntimeModel):
    status: str = "STOPPED"
    managed_run_id: str | None = None
    started_at: str | None = None
    evaluation_execution: str | None = None
    components: list[RuntimeComponentSnapshot] = Field(default_factory=list)


class ResearchIntentSnapshot(RuntimeModel):
    status: Literal["AVAILABLE", "NOT_AVAILABLE"] = "NOT_AVAILABLE"
    generation: int | None = None
    intent_status: str | None = None
    mode: str | None = None
    parent_ids: list[str] = Field(default_factory=list)
    operation_count: int = 0
    repair_attempts: int = 0


class ResearchRuntimeSnapshot(RuntimeModel):
    status: str = "NOT_STARTED"
    research_run_id: str | None = None
    current_generation: int | None = None
    current_phase: str = "UNKNOWN"
    completed_generations: int = 0
    requested_generations: int = 0
    completion_percent: float = 0.0
    last_completed_generation: int | None = None
    last_completed_status: str | None = None
    last_non_degraded_generation: int | None = None
    phase_started_at: str | None = None
    phase_age_seconds: float | None = None
    last_event: str | None = None
    last_event_at: str | None = None
    last_event_age_seconds: float | None = None
    stale_after_seconds: float | None = None
    is_stale: bool = False
    consistency_status: Literal["OK", "WARN", "UNKNOWN"] = "UNKNOWN"
    consistency_issues: list[str] = Field(default_factory=list)
    repair_attempt: int | None = None
    repair_attempts_allowed: int | None = None
    error_class: str | None = None
    timing_summary: dict[str, object] = Field(default_factory=dict)
    current_intent: ResearchIntentSnapshot = Field(default_factory=ResearchIntentSnapshot)


class EvaluationJobSnapshot(RuntimeModel):
    job_id: str
    status: str
    queue_attempt: int = 0
    max_attempts: int = 1
    retries_used: int = 0
    attempts_remaining: int = 0
    retry_pending: bool = False
    error_class: str | None = None
    lease_until: str | None = None
    lease_expired: bool = False


class EvaluationAttemptSnapshot(RuntimeModel):
    job_id: str | None = None
    status: str | None = None
    queue_attempt: int | None = None
    max_attempts: int | None = None
    error_class: str | None = None
    execution_mode: str | None = None
    isolated: bool = False
    timeout_enforced: bool = False
    research_run_id: str | None = None
    attempt_id: str | None = None
    generation: int | None = None


class EvaluationRetrySummary(RuntimeModel):
    jobs_with_retries: int = 0
    retries_used: int = 0
    retry_pending_jobs: int = 0
    retry_exhausted_jobs: int = 0


class LatestEvaluationJobSnapshot(RuntimeModel):
    job_id: str | None = None
    status: str | None = None
    queue_attempt: int | None = None
    max_attempts: int | None = None
    error_class: str | None = None
    execution_mode: str | None = None
    isolated: bool = False
    timeout_enforced: bool = False
    research_run_id: str | None = None
    attempt_id: str | None = None
    generation: int | None = None


class EvaluationRuntimeSnapshot(RuntimeModel):
    status: str = "READY"
    queue_health: Literal["HEALTHY", "WARN", "UNAVAILABLE"] = "HEALTHY"
    queue_issues: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    total_jobs: int = 0
    terminal_jobs: int = 0
    retry_summary: EvaluationRetrySummary = Field(default_factory=EvaluationRetrySummary)
    active_jobs: list[EvaluationJobSnapshot] = Field(default_factory=list)
    queued_jobs: list[EvaluationJobSnapshot] = Field(default_factory=list)
    recent_terminal_jobs: list[EvaluationJobSnapshot] = Field(default_factory=list)
    recent_attempts: list[EvaluationAttemptSnapshot] = Field(default_factory=list)
    latest_job: LatestEvaluationJobSnapshot | None = None


class EvidenceRuntimeSnapshot(RuntimeModel):
    status: str = "NOT_LINKED"
    link_status: Literal[
        "NOT_LINKED", "LINKED", "MISSING_RUN", "INTEGRITY_ERROR"
    ] = "NOT_LINKED"
    integrity_status: Literal[
        "NOT_PRESENT", "VERIFIED", "INTEGRITY_ERROR"
    ] = "NOT_PRESENT"
    research_run_id: str | None = None
    event_count: int = 0
    manifest_present: bool = False
    attempt_count: int = 0
    generation_count: int = 0
    last_event_id: str | None = None
    last_event_kind: str | None = None
    last_attempt_id: str | None = None
    last_attempt_status: str | None = None
    last_generation: int | None = None
    last_generation_status: str | None = None
    terminal_status: str | None = None
    closed: bool = False


class WorkerRuntimeSnapshot(RuntimeModel):
    worker_id: str
    job_id: str | None = None
    role: str = "unknown"
    status: str = "UNKNOWN"
    last_heartbeat: str | None = None
    online_state: Literal["ONLINE", "STALE", "OFFLINE", "UNKNOWN"] = "UNKNOWN"
    attempt: int = 0
    error_class: str | None = None


class LLMRuntimeSnapshot(RuntimeModel):
    provider: str = "codex_desktop"
    status: str = "UNKNOWN"
    last_result: str = "UNKNOWN"
    last_call_at: str | None = None
    operation: str | None = None


class RecoveryRuntimeSnapshot(RuntimeModel):
    status: Literal["NONE", "RECOVERED", "INTERRUPTED"] = "NONE"
    last_event: str | None = None
    last_event_at: str | None = None
    reconciled_jobs: list[str] = Field(default_factory=list)
    cancelled_orphaned_jobs: list[str] = Field(default_factory=list)
    interrupted_research_run_id: str | None = None
    evidence_closed: bool | None = None


class KnowledgeRuntimeSnapshot(RuntimeModel):
    status: Literal["CONNECTED", "MISSING", "INVALID"] = "MISSING"
    source: Literal["EVIDENCE_PROJECTION"] = "EVIDENCE_PROJECTION"
    sync_status: Literal[
        "NOT_APPLICABLE",
        "IN_SYNC",
        "STALE",
        "MISSING",
        "INVALID",
        "EVIDENCE_INTEGRITY_ERROR",
    ] = "NOT_APPLICABLE"
    known_good_count: int = 0
    known_bad_count: int = 0
    unexplored_count: int = 0
    interactions_count: int = 0
    evidence_experiment_count: int = 0
    projected_experiment_count: int = 0
    missing_experiment_count: int = 0
    unverified_entry_count: int = 0
    projection_coverage_percent: float = 100.0


class StrategyStateRuntimeSnapshot(RuntimeModel):
    champion_status: str = "MISSING"
    champion_hash: str | None = None
    champion_family: str | None = None
    champion_generation: int | None = None
    champion_score: float | None = None
    champion_evidence_status: Literal[
        "NO_CHAMPION", "LINKED", "NOT_FOUND", "EVIDENCE_INTEGRITY_ERROR"
    ] = "NO_CHAMPION"
    champion_research_run_id: str | None = None
    champion_attempt_id: str | None = None
    champion_candidate_status: str | None = None
    promotion_audit_status: Literal[
        "NOT_APPLICABLE", "PRESENT", "MISSING", "INVALID"
    ] = "NOT_APPLICABLE"
    promotion_audit_records: int = 0
    last_promotion_at: str | None = None
    frontier_status: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"
    rescue_status: Literal["NOT_CONNECTED"] = "NOT_CONNECTED"


class RuntimeErrorSummary(RuntimeModel):
    source: str
    error_class: str


class RuntimeSnapshot(RuntimeModel):
    schema_version: int = 2
    system: ManagedSystemSnapshot = Field(default_factory=ManagedSystemSnapshot)
    research: ResearchRuntimeSnapshot = Field(default_factory=ResearchRuntimeSnapshot)
    evaluation: EvaluationRuntimeSnapshot = Field(default_factory=EvaluationRuntimeSnapshot)
    evidence: EvidenceRuntimeSnapshot = Field(default_factory=EvidenceRuntimeSnapshot)
    workers: list[WorkerRuntimeSnapshot] = Field(default_factory=list)
    llm: LLMRuntimeSnapshot = Field(default_factory=LLMRuntimeSnapshot)
    recovery: RecoveryRuntimeSnapshot = Field(default_factory=RecoveryRuntimeSnapshot)
    knowledge: KnowledgeRuntimeSnapshot = Field(default_factory=KnowledgeRuntimeSnapshot)
    strategy_state: StrategyStateRuntimeSnapshot = Field(
        default_factory=StrategyStateRuntimeSnapshot
    )
    recent_errors: list[RuntimeErrorSummary] = Field(default_factory=list)
    orders_enabled: Literal[False] = False
