from __future__ import annotations

from fastapi import FastAPI

from finance_autoresearch.state.models import (
    AnalysisRecord,
    BrainNoteRecord,
    CandidateFrontierRecord,
    CommandRecord,
    ExperimentRecord,
    FamilyMemoryRecord,
    FalsificationRecord,
    IterationHistoryRecord,
    KnowledgeRecord,
    LessonRecord,
    LessonGraphRecord,
    OutboxMessage,
    ResearchPlanRecord,
    RunRecord,
    TrialRecord,
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
    def history_commands(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [_serialize_command(record) for record in store.list_commands(limit=_fetch_limit(limit, run_id, iteration))]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/experiments")
    def history_experiments(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_experiment(record)
            for record in store.list_experiments(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/analysis")
    def history_analysis(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_analysis(record)
            for record in store.list_analyses(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/runs")
    def history_runs(limit: int = 50, run_id: str | None = None) -> list[dict[str, object]]:
        records = [_serialize_run(record) for record in store.list_runs(limit=_fetch_limit(limit, run_id, None))]
        return _filter_history_payload(records, run_id=run_id, iteration=None)[:limit]

    @app.get("/history/research-plans")
    def history_research_plans(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_research_plan(record)
            for record in store.list_research_plans(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/knowledge")
    def history_knowledge(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_knowledge(record)
            for record in store.list_knowledge(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/lessons")
    def history_lessons(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_lesson(record)
            for record in store.list_lessons(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/iterations")
    def history_iterations(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = _serialize_iteration_history(
            store=store,
            limit=_fetch_limit(limit, run_id, iteration),
        )
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/outbox")
    def history_outbox(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_outbox(record)
            for record in store.list_outbox(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/brain-notes")
    def history_brain_notes(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_brain_note(record)
            for record in store.list_brain_notes(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/brain-maps")
    def history_brain_maps(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_brain_note(record)
            for record in store.list_brain_maps(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/trials")
    def history_trials(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_trial(record)
            for record in store.list_trials(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/falsification")
    def history_falsification(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_falsification(record)
            for record in store.list_falsifications(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/frontier")
    def history_frontier(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_candidate_frontier(record)
            for record in store.list_candidate_frontier(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/lesson-graph")
    def history_lesson_graph(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_lesson_graph(record)
            for record in store.list_lesson_graph(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

    @app.get("/history/family-memory")
    def history_family_memory(
        limit: int = 50,
        run_id: str | None = None,
        iteration: int | None = None,
    ) -> list[dict[str, object]]:
        records = [
            _serialize_family_memory(record)
            for record in store.list_family_memory(limit=_fetch_limit(limit, run_id, iteration))
        ]
        return _filter_history_payload(records, run_id=run_id, iteration=iteration)[:limit]

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


def _serialize_run(record: RunRecord) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "project_id": record.project_id,
        "state": record.state,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_research_plan(record: ResearchPlanRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "hypothesis": record.hypothesis,
        "summary": record.summary,
        "plan_output": record.plan_output,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_knowledge(record: KnowledgeRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "source_path": record.source_path,
        "title": record.title,
        "excerpt": record.excerpt,
        "metadata": record.metadata,
        "created_at": serialize_datetime(record.created_at),
    }


def _serialize_lesson(record: LessonRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "decision": record.decision,
        "summary": record.summary,
        "lesson_output": record.lesson_output,
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


def _fetch_limit(limit: int, run_id: str | None, iteration: int | None) -> int:
    if run_id is None and iteration is None:
        return limit
    return max(limit * 10, 200)


def _filter_history_payload(
    records: list[dict[str, object]],
    *,
    run_id: str | None,
    iteration: int | None,
) -> list[dict[str, object]]:
    filtered = records
    if run_id is not None:
        filtered = [record for record in filtered if _record_run_id(record) == run_id]
    if iteration is not None:
        filtered = [
            record for record in filtered if _record_iteration(record) == iteration
        ]
    return filtered


def _record_run_id(record: dict[str, object]) -> str | None:
    for key in ("run_id", "linked_run_id"):
        value = record.get(key)
        if isinstance(value, str):
            return value
    payload = record.get("payload")
    if isinstance(payload, dict):
        value = payload.get("run_id")
        if isinstance(value, str):
            return value
    return None


def _record_iteration(record: dict[str, object]) -> int | None:
    for key in ("iteration", "linked_iteration"):
        value = record.get(key)
        if isinstance(value, int):
            return value
    payload = record.get("payload")
    if isinstance(payload, dict):
        value = payload.get("iteration")
        if isinstance(value, int):
            return value
    return None


def _serialize_brain_note(record: BrainNoteRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "note_type": record.note_type,
        "path": record.path,
        "title": record.title,
        "generated": record.generated,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "revision": record.revision,
        "metadata": record.metadata,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_trial(record: TrialRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "family": record.family,
        "artifact_kind": record.artifact_kind,
        "candidate_revision": record.candidate_revision,
        "baseline_revision": record.baseline_revision,
        "compile_status": record.compile_status,
        "falsification_pass": record.falsification_pass,
        "decision": record.decision,
        "metadata": record.metadata,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_falsification(record: FalsificationRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "candidate_revision": record.candidate_revision,
        "passed": record.passed,
        "checks": record.checks,
        "summary": record.summary,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_lesson_graph(record: LessonGraphRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "decision": record.decision,
        "thesis": record.thesis,
        "mutation_delta": record.mutation_delta,
        "observed_outcome": record.observed_outcome,
        "failure_mode": record.failure_mode,
        "next_action": record.next_action,
        "confidence": record.confidence,
        "novelty_score": record.novelty_score,
        "knowledge_source_ids": list(record.knowledge_source_ids),
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_family_memory(record: FamilyMemoryRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "family": record.family,
        "symbol_scope": record.symbol_scope,
        "timeframe_scope": record.timeframe_scope,
        "regime_scope": record.regime_scope,
        "outcome": record.outcome,
        "linked_run_id": record.linked_run_id,
        "linked_iteration": record.linked_iteration,
        "novelty_score": record.novelty_score,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_candidate_frontier(record: CandidateFrontierRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "project_id": record.project_id,
        "run_id": record.run_id,
        "iteration": record.iteration,
        "candidate_id": record.candidate_id,
        "rank": record.rank,
        "promoted": record.promoted,
        "prescreen_reason": record.prescreen_reason,
        "prescreen_score": record.prescreen_score,
        "metadata": record.metadata,
        "created_at": serialize_datetime(record.created_at),
        "updated_at": serialize_datetime(record.updated_at),
    }


def _serialize_iteration_history(
    *,
    store: StateRepository,
    limit: int,
) -> list[dict[str, object]]:
    return [
        _serialize_iteration_entry(record)
        for record in store.list_iteration_history(limit=limit)
    ]


def _serialize_iteration_entry(record: IterationHistoryRecord) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "iteration": record.iteration,
        "run": _serialize_run(record.run) if record.run is not None else None,
        "decision": record.decision,
        "experiment": _serialize_experiment(record.experiment)
        if record.experiment is not None
        else None,
        "analysis": _serialize_analysis(record.analysis)
        if record.analysis is not None
        else None,
        "research_plan": _serialize_research_plan(record.research_plan)
        if record.research_plan is not None
        else None,
        "lesson": _serialize_lesson(record.lesson) if record.lesson is not None else None,
        "trial": _serialize_trial(record.trial) if record.trial is not None else None,
        "falsification": _serialize_falsification(record.falsification)
        if record.falsification is not None
        else None,
        "lesson_graph": _serialize_lesson_graph(record.lesson_graph)
        if record.lesson_graph is not None
        else None,
        "family_memory": _serialize_family_memory(record.family_memory)
        if record.family_memory is not None
        else None,
        "frontier": [
            _serialize_candidate_frontier(item) for item in record.frontier
        ],
        "linked_brain_notes": [
            _serialize_brain_note(item) for item in record.linked_brain_notes
        ],
        "last_updated_at": serialize_datetime(record.last_updated_at),
    }
