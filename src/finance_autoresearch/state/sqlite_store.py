from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
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
    ProjectStatus,
    ResearchPlanRecord,
    RunRecord,
    TrialRecord,
    WorkerName,
    ensure_utc,
    parse_datetime,
    serialize_datetime,
    utc_now,
)
from .outbox import SQLiteOutbox
from .repository import StateRepository


class SQLiteStateStore(StateRepository):
    def __init__(self, *, db_path: Path, project_id: str) -> None:
        self._db_path = Path(db_path).resolve()
        self._project_id = project_id
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._initialize_schema()
        self._ensure_default_status()
        self._outbox = SQLiteOutbox(self._connection, project_id)

    def close(self) -> None:
        self._connection.close()

    def get_status(self) -> ProjectStatus:
        cursor = self._connection.execute(
            """
            SELECT
                project_id,
                project_state,
                pipeline_state,
                autoresearch_state,
                active_run_id,
                current_stage,
                pending_command,
                pipeline_heartbeat_at,
                autoresearch_heartbeat_at,
                candidate_revision,
                baseline_revision,
                recovery_marker
            FROM project_status
            WHERE project_id = ?
            """,
            (self._project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            self._ensure_default_status()
            return self.get_status()
        return self._row_to_status(row)

    def set_status(
        self,
        *,
        project_state: str | None = None,
        pipeline_state: str | None = None,
        autoresearch_state: str | None = None,
    ) -> ProjectStatus:
        changes: dict[str, Any] = {}
        if project_state is not None:
            changes["project_state"] = project_state
        if pipeline_state is not None:
            changes["pipeline_state"] = pipeline_state
        if autoresearch_state is not None:
            changes["autoresearch_state"] = autoresearch_state
        return self._update_status(**changes)

    def record_command(
        self,
        command: str,
        *,
        source: str,
        requested_by: str,
        requested_at: datetime | None = None,
        payload: Mapping[str, Any] | None = None,
        accepted: bool,
        project_state: str,
        pipeline_state: str,
        autoresearch_state: str,
        pending_command: str | None,
        message: str,
        run_id: str | None,
    ) -> CommandRecord:
        request_timestamp = ensure_utc(requested_at or utc_now())
        payload_json = self._serialize_json(payload or {})
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO command_history (
                    project_id,
                    command,
                    source,
                    requested_by,
                    requested_at,
                    payload_json,
                    accepted,
                    project_state,
                    pipeline_state,
                    autoresearch_state,
                    pending_command,
                    message,
                    run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    command,
                    source,
                    requested_by,
                    serialize_datetime(request_timestamp),
                    payload_json,
                    int(accepted),
                    project_state,
                    pipeline_state,
                    autoresearch_state,
                    pending_command,
                    message,
                    run_id,
                ),
            )

        return CommandRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            command=command,
            source=source,
            requested_by=requested_by,
            requested_at=request_timestamp,
            payload=dict(payload or {}),
            accepted=accepted,
            project_state=project_state,
            pipeline_state=pipeline_state,
            autoresearch_state=autoresearch_state,
            pending_command=pending_command,
            message=message,
            run_id=run_id,
        )

    def list_commands(self, *, limit: int = 50) -> list[CommandRecord]:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                command,
                source,
                requested_by,
                requested_at,
                payload_json,
                accepted,
                project_state,
                pipeline_state,
                autoresearch_state,
                pending_command,
                message,
                run_id
            FROM command_history
            WHERE project_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_command(row) for row in cursor.fetchall()]

    def record_run(
        self,
        *,
        run_id: str,
        state: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> RunRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        with self._connection:
            existing = self._connection.execute(
                """
                SELECT created_at
                FROM run_history
                WHERE project_id = ? AND run_id = ?
                """,
                (self._project_id, run_id),
            ).fetchone()
            persisted_created_at = parse_datetime(existing["created_at"]) if existing else None
            created_timestamp = persisted_created_at or created_timestamp
            self._connection.execute(
                """
                INSERT INTO run_history (
                    run_id,
                    project_id,
                    state,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, run_id)
                DO UPDATE SET
                    state = excluded.state,
                    updated_at = excluded.updated_at
                """,
                (
                    run_id,
                    self._project_id,
                    state,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )
        return RunRecord(
            run_id=run_id,
            project_id=self._project_id,
            state=state,
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def get_latest_run(self) -> RunRecord | None:
        cursor = self._connection.execute(
            """
            SELECT run_id, project_id, state, created_at, updated_at
            FROM run_history
            WHERE project_id = ?
            ORDER BY created_at DESC, run_id DESC
            LIMIT 1
            """,
            (self._project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    def list_runs(self, *, limit: int = 50) -> list[RunRecord]:
        cursor = self._connection.execute(
            """
            SELECT run_id, project_id, state, created_at, updated_at
            FROM run_history
            WHERE project_id = ?
            ORDER BY created_at DESC, run_id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_run(row) for row in cursor.fetchall()]

    def list_iteration_history(
        self,
        *,
        limit: int = 50,
    ) -> list[IterationHistoryRecord]:
        experiments = self.list_experiments(limit=limit)
        if not experiments:
            return []

        run_keys = {record.run_id for record in experiments}
        iteration_keys = {(record.run_id, record.iteration) for record in experiments}
        runs = self._fetch_runs_for_ids(run_keys)
        analyses = self._fetch_related_rows(
            table="analysis_history",
            row_factory=self._row_to_analysis,
            limit=limit,
            iteration_keys=iteration_keys,
        )
        research_plans = self._fetch_related_rows(
            table="research_plan_history",
            row_factory=self._row_to_research_plan,
            limit=limit,
            iteration_keys=iteration_keys,
        )
        lessons = self._fetch_related_rows(
            table="lesson_history",
            row_factory=self._row_to_lesson,
            limit=limit,
            iteration_keys=iteration_keys,
        )
        trials = self._fetch_related_rows(
            table="trial_history",
            row_factory=self._row_to_trial,
            limit=limit,
            iteration_keys=iteration_keys,
        )
        falsifications = self._fetch_related_rows(
            table="falsification_history",
            row_factory=self._row_to_falsification,
            limit=limit,
            iteration_keys=iteration_keys,
        )
        lesson_graphs = self._fetch_related_rows(
            table="lesson_graph_history",
            row_factory=self._row_to_lesson_graph,
            limit=limit,
            iteration_keys=iteration_keys,
        )
        family_memory = self._fetch_family_memory_rows(limit=limit, iteration_keys=iteration_keys)
        frontier = self._fetch_frontier_rows(limit=limit * 4, iteration_keys=iteration_keys)
        brain_notes = self._fetch_brain_notes_for_iterations(
            limit=limit * 8,
            iteration_keys=iteration_keys,
        )

        items: list[IterationHistoryRecord] = []
        for experiment in experiments:
            key = (experiment.run_id, experiment.iteration)
            run_record = runs.get(experiment.run_id)
            analysis_record = analyses.get(key)
            research_plan_record = research_plans.get(key)
            lesson_record = lessons.get(key)
            trial_record = trials.get(key)
            falsification_record = falsifications.get(key)
            lesson_graph_record = lesson_graphs.get(key)
            family_memory_record = family_memory.get(key)
            frontier_records = tuple(frontier.get(key, ()))
            linked_notes = tuple(brain_notes.get(key, ()))
            last_updated_at = max(
                timestamp
                for timestamp in (
                    experiment.updated_at,
                    analysis_record.updated_at if analysis_record is not None else None,
                    research_plan_record.updated_at
                    if research_plan_record is not None
                    else None,
                    lesson_record.updated_at if lesson_record is not None else None,
                    trial_record.updated_at if trial_record is not None else None,
                    falsification_record.updated_at
                    if falsification_record is not None
                    else None,
                    lesson_graph_record.updated_at
                    if lesson_graph_record is not None
                    else None,
                    family_memory_record.updated_at
                    if family_memory_record is not None
                    else None,
                    frontier_records[0].updated_at if frontier_records else None,
                    linked_notes[0].updated_at if linked_notes else None,
                    run_record.updated_at if run_record is not None else None,
                )
                if timestamp is not None
            )
            items.append(
                IterationHistoryRecord(
                    run_id=experiment.run_id,
                    iteration=experiment.iteration,
                    run=run_record,
                    decision=experiment.decision,
                    experiment=experiment,
                    analysis=analysis_record,
                    research_plan=research_plan_record,
                    lesson=lesson_record,
                    trial=trial_record,
                    falsification=falsification_record,
                    lesson_graph=lesson_graph_record,
                    family_memory=family_memory_record,
                    frontier=frontier_records,
                    linked_brain_notes=linked_notes,
                    last_updated_at=last_updated_at,
                )
            )
        items.sort(
            key=lambda record: (
                record.last_updated_at or record.experiment.updated_at,
                record.run_id,
                record.iteration,
            ),
            reverse=True,
        )
        return items

    def get_iteration_history_entry(
        self,
        *,
        run_id: str,
        iteration: int,
    ) -> IterationHistoryRecord | None:
        record = self._fetch_experiment_by_run_iteration(run_id=run_id, iteration=iteration)
        if record is None:
            return None
        run_record = self._fetch_runs_for_ids({run_id}).get(run_id)
        key = {(run_id, iteration)}
        analysis_record = self._fetch_related_rows(
            table="analysis_history",
            row_factory=self._row_to_analysis,
            limit=1,
            iteration_keys=key,
        ).get((run_id, iteration))
        research_plan_record = self._fetch_related_rows(
            table="research_plan_history",
            row_factory=self._row_to_research_plan,
            limit=1,
            iteration_keys=key,
        ).get((run_id, iteration))
        lesson_record = self._fetch_related_rows(
            table="lesson_history",
            row_factory=self._row_to_lesson,
            limit=1,
            iteration_keys=key,
        ).get((run_id, iteration))
        trial_record = self._fetch_related_rows(
            table="trial_history",
            row_factory=self._row_to_trial,
            limit=1,
            iteration_keys=key,
        ).get((run_id, iteration))
        falsification_record = self._fetch_related_rows(
            table="falsification_history",
            row_factory=self._row_to_falsification,
            limit=1,
            iteration_keys=key,
        ).get((run_id, iteration))
        lesson_graph_record = self._fetch_related_rows(
            table="lesson_graph_history",
            row_factory=self._row_to_lesson_graph,
            limit=1,
            iteration_keys=key,
        ).get((run_id, iteration))
        family_memory_record = self._fetch_family_memory_rows(limit=1, iteration_keys=key).get(
            (run_id, iteration)
        )
        frontier_records = tuple(
            self._fetch_frontier_rows(limit=10, iteration_keys=key).get((run_id, iteration), ())
        )
        linked_notes = tuple(
            self._fetch_brain_notes_for_iterations(limit=20, iteration_keys=key).get(
                (run_id, iteration),
                (),
            )
        )
        last_updated_at = max(
            timestamp
            for timestamp in (
                record.updated_at,
                analysis_record.updated_at if analysis_record is not None else None,
                research_plan_record.updated_at
                if research_plan_record is not None
                else None,
                lesson_record.updated_at if lesson_record is not None else None,
                trial_record.updated_at if trial_record is not None else None,
                falsification_record.updated_at if falsification_record is not None else None,
                lesson_graph_record.updated_at if lesson_graph_record is not None else None,
                family_memory_record.updated_at if family_memory_record is not None else None,
                frontier_records[0].updated_at if frontier_records else None,
                linked_notes[0].updated_at if linked_notes else None,
                run_record.updated_at if run_record is not None else None,
            )
            if timestamp is not None
        )
        return IterationHistoryRecord(
            run_id=run_id,
            iteration=iteration,
            run=run_record,
            decision=record.decision,
            experiment=record,
            analysis=analysis_record,
            research_plan=research_plan_record,
            lesson=lesson_record,
            trial=trial_record,
            falsification=falsification_record,
            lesson_graph=lesson_graph_record,
            family_memory=family_memory_record,
            frontier=frontier_records,
            linked_brain_notes=linked_notes,
            last_updated_at=last_updated_at,
        )

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
    ) -> ExperimentRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        metrics_json = self._serialize_json(backtest_metrics)
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO experiment_history (
                    project_id,
                    run_id,
                    iteration,
                    candidate_revision,
                    baseline_revision,
                    hypothesis,
                    mutation_summary,
                    backtest_metrics_json,
                    decision,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    candidate_revision,
                    baseline_revision,
                    hypothesis,
                    mutation_summary,
                    metrics_json,
                    decision,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )

        return ExperimentRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            candidate_revision=candidate_revision,
            baseline_revision=baseline_revision,
            hypothesis=hypothesis,
            mutation_summary=mutation_summary,
            backtest_metrics=dict(backtest_metrics),
            decision=decision,
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def get_latest_experiment(self) -> ExperimentRecord | None:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                candidate_revision,
                baseline_revision,
                hypothesis,
                mutation_summary,
                backtest_metrics_json,
                decision,
                created_at,
                updated_at
            FROM experiment_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (self._project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_experiment(row)

    def list_experiments(self, *, limit: int = 50) -> list[ExperimentRecord]:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                candidate_revision,
                baseline_revision,
                hypothesis,
                mutation_summary,
                backtest_metrics_json,
                decision,
                created_at,
                updated_at
            FROM experiment_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_experiment(row) for row in cursor.fetchall()]

    def record_analysis(
        self,
        *,
        run_id: str,
        iteration: int,
        analysis_output: Mapping[str, Any],
        summary: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> AnalysisRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        analysis_json = self._serialize_json(analysis_output)
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO analysis_history (
                    project_id,
                    run_id,
                    iteration,
                    analysis_output_json,
                    summary,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    analysis_json,
                    summary,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )

        return AnalysisRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            analysis_output=dict(analysis_output),
            summary=summary,
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def get_latest_analysis(self) -> AnalysisRecord | None:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                analysis_output_json,
                summary,
                created_at,
                updated_at
            FROM analysis_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (self._project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_analysis(row)

    def list_analyses(self, *, limit: int = 50) -> list[AnalysisRecord]:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                analysis_output_json,
                summary,
                created_at,
                updated_at
            FROM analysis_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_analysis(row) for row in cursor.fetchall()]

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
    ) -> ResearchPlanRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        plan_json = self._serialize_json(plan_output)
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO research_plan_history (
                    project_id,
                    run_id,
                    iteration,
                    hypothesis,
                    summary,
                    plan_output_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    hypothesis,
                    summary,
                    plan_json,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )

        return ResearchPlanRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            hypothesis=hypothesis,
            summary=summary,
            plan_output=dict(plan_output),
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def get_latest_research_plan(self) -> ResearchPlanRecord | None:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                hypothesis,
                summary,
                plan_output_json,
                created_at,
                updated_at
            FROM research_plan_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (self._project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_research_plan(row)

    def list_research_plans(self, *, limit: int = 50) -> list[ResearchPlanRecord]:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                hypothesis,
                summary,
                plan_output_json,
                created_at,
                updated_at
            FROM research_plan_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_research_plan(row) for row in cursor.fetchall()]

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
    ) -> KnowledgeRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        metadata_json = self._serialize_json(metadata)
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO knowledge_history (
                    project_id,
                    run_id,
                    iteration,
                    source_path,
                    title,
                    excerpt,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    source_path,
                    title,
                    excerpt,
                    metadata_json,
                    serialize_datetime(created_timestamp),
                ),
            )

        return KnowledgeRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            source_path=source_path,
            title=title,
            excerpt=excerpt,
            metadata=dict(metadata),
            created_at=created_timestamp,
        )

    def list_knowledge(self, *, limit: int = 50) -> list[KnowledgeRecord]:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                source_path,
                title,
                excerpt,
                metadata_json,
                created_at
            FROM knowledge_history
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_knowledge(row) for row in cursor.fetchall()]

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
    ) -> LessonRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        lesson_json = self._serialize_json(lesson_output)
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO lesson_history (
                    project_id,
                    run_id,
                    iteration,
                    decision,
                    summary,
                    lesson_output_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    decision,
                    summary,
                    lesson_json,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )

        return LessonRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            decision=decision,
            summary=summary,
            lesson_output=dict(lesson_output),
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def get_latest_lesson(self) -> LessonRecord | None:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                decision,
                summary,
                lesson_output_json,
                created_at,
                updated_at
            FROM lesson_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (self._project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_lesson(row)

    def list_lessons(self, *, limit: int = 50) -> list[LessonRecord]:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                decision,
                summary,
                lesson_output_json,
                created_at,
                updated_at
            FROM lesson_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_lesson(row) for row in cursor.fetchall()]

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
    ) -> BrainNoteRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        metadata_json = self._serialize_json(metadata or {})
        with self._connection:
            existing = self._connection.execute(
                """
                SELECT created_at
                FROM brain_note_registry
                WHERE project_id = ? AND path = ?
                """,
                (self._project_id, path),
            ).fetchone()
            persisted_created_at = parse_datetime(existing["created_at"]) if existing else None
            created_timestamp = persisted_created_at or created_timestamp
            self._connection.execute(
                """
                INSERT INTO brain_note_registry (
                    project_id,
                    note_type,
                    path,
                    title,
                    generated,
                    run_id,
                    iteration,
                    revision,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, path)
                DO UPDATE SET
                    note_type = excluded.note_type,
                    title = excluded.title,
                    generated = excluded.generated,
                    run_id = excluded.run_id,
                    iteration = excluded.iteration,
                    revision = excluded.revision,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    self._project_id,
                    note_type,
                    path,
                    title,
                    int(generated),
                    run_id,
                    iteration,
                    revision,
                    metadata_json,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )
        cursor = self._connection.execute(
            """
            SELECT *
            FROM brain_note_registry
            WHERE project_id = ? AND path = ?
            """,
            (self._project_id, path),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError("brain_note_registry upsert failed")
        return self._row_to_brain_note(row)

    def list_brain_notes(
        self,
        *,
        limit: int = 50,
        note_type: str | None = None,
    ) -> list[BrainNoteRecord]:
        parameters: list[Any] = [self._project_id]
        where = "WHERE project_id = ?"
        if note_type is not None:
            where += " AND note_type = ?"
            parameters.append(note_type)
        parameters.append(limit)
        cursor = self._connection.execute(
            f"""
            SELECT *
            FROM brain_note_registry
            {where}
            ORDER BY updated_at DESC, created_at DESC, path ASC, id ASC
            LIMIT ?
            """,
            tuple(parameters),
        )
        return [self._row_to_brain_note(row) for row in cursor.fetchall()]

    def list_brain_maps(self, *, limit: int = 50) -> list[BrainNoteRecord]:
        cursor = self._connection.execute(
            """
            SELECT *
            FROM brain_note_registry
            WHERE project_id = ? AND note_type = ?
            ORDER BY path ASC, title ASC, id ASC
            LIMIT ?
            """,
            (self._project_id, "map", limit),
        )
        return [self._row_to_brain_note(row) for row in cursor.fetchall()]

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
    ) -> TrialRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        metadata_json = self._serialize_json(metadata or {})
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO trial_history (
                    project_id,
                    run_id,
                    iteration,
                    family,
                    artifact_kind,
                    candidate_revision,
                    baseline_revision,
                    compile_status,
                    falsification_pass,
                    decision,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    family,
                    artifact_kind,
                    candidate_revision,
                    baseline_revision,
                    compile_status,
                    int(falsification_pass),
                    decision,
                    metadata_json,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )
        return TrialRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            family=family,
            artifact_kind=artifact_kind,
            candidate_revision=candidate_revision,
            baseline_revision=baseline_revision,
            compile_status=compile_status,
            falsification_pass=falsification_pass,
            decision=decision,
            metadata=dict(metadata or {}),
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def list_trials(self, *, limit: int = 50) -> list[TrialRecord]:
        cursor = self._connection.execute(
            """
            SELECT *
            FROM trial_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_trial(row) for row in cursor.fetchall()]

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
    ) -> FalsificationRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        checks_json = self._serialize_json(checks)
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO falsification_history (
                    project_id,
                    run_id,
                    iteration,
                    candidate_revision,
                    passed,
                    checks_json,
                    summary,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    candidate_revision,
                    int(passed),
                    checks_json,
                    summary,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )
        return FalsificationRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            candidate_revision=candidate_revision,
            passed=passed,
            checks=dict(checks),
            summary=summary,
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def list_falsifications(self, *, limit: int = 50) -> list[FalsificationRecord]:
        cursor = self._connection.execute(
            """
            SELECT *
            FROM falsification_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_falsification(row) for row in cursor.fetchall()]

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
    ) -> LessonGraphRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        knowledge_source_ids_json = self._serialize_json(
            {"knowledge_source_ids": list(knowledge_source_ids)}
        )
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO lesson_graph_history (
                    project_id,
                    run_id,
                    iteration,
                    decision,
                    thesis,
                    mutation_delta,
                    observed_outcome,
                    failure_mode,
                    next_action,
                    confidence,
                    novelty_score,
                    knowledge_source_ids_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    decision,
                    thesis,
                    mutation_delta,
                    observed_outcome,
                    failure_mode,
                    next_action,
                    confidence,
                    float(novelty_score),
                    knowledge_source_ids_json,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )
        return LessonGraphRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            decision=decision,
            thesis=thesis,
            mutation_delta=mutation_delta,
            observed_outcome=observed_outcome,
            failure_mode=failure_mode,
            next_action=next_action,
            confidence=confidence,
            novelty_score=float(novelty_score),
            knowledge_source_ids=tuple(knowledge_source_ids),
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def list_lesson_graph(self, *, limit: int = 50) -> list[LessonGraphRecord]:
        cursor = self._connection.execute(
            """
            SELECT *
            FROM lesson_graph_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_lesson_graph(row) for row in cursor.fetchall()]

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
    ) -> FamilyMemoryRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO family_memory_history (
                    project_id,
                    family,
                    symbol_scope,
                    timeframe_scope,
                    regime_scope,
                    outcome,
                    linked_run_id,
                    linked_iteration,
                    novelty_score,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    family,
                    symbol_scope,
                    timeframe_scope,
                    regime_scope,
                    outcome,
                    linked_run_id,
                    linked_iteration,
                    float(novelty_score),
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )
        return FamilyMemoryRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            family=family,
            symbol_scope=symbol_scope,
            timeframe_scope=timeframe_scope,
            regime_scope=regime_scope,
            outcome=outcome,
            linked_run_id=linked_run_id,
            linked_iteration=linked_iteration,
            novelty_score=float(novelty_score),
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def list_family_memory(self, *, limit: int = 50) -> list[FamilyMemoryRecord]:
        cursor = self._connection.execute(
            """
            SELECT *
            FROM family_memory_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_family_memory(row) for row in cursor.fetchall()]

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
    ) -> CandidateFrontierRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        updated_timestamp = ensure_utc(updated_at or created_timestamp)
        metadata_json = self._serialize_json(metadata or {})
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO candidate_frontier_history (
                    project_id,
                    run_id,
                    iteration,
                    candidate_id,
                    rank,
                    promoted,
                    prescreen_reason,
                    prescreen_score,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._project_id,
                    run_id,
                    iteration,
                    candidate_id,
                    rank,
                    int(promoted),
                    prescreen_reason,
                    float(prescreen_score),
                    metadata_json,
                    serialize_datetime(created_timestamp),
                    serialize_datetime(updated_timestamp),
                ),
            )
        return CandidateFrontierRecord(
            id=int(cursor.lastrowid),
            project_id=self._project_id,
            run_id=run_id,
            iteration=iteration,
            candidate_id=candidate_id,
            rank=rank,
            promoted=promoted,
            prescreen_reason=prescreen_reason,
            prescreen_score=float(prescreen_score),
            metadata=dict(metadata or {}),
            created_at=created_timestamp,
            updated_at=updated_timestamp,
        )

    def list_candidate_frontier(self, *, limit: int = 50) -> list[CandidateFrontierRecord]:
        cursor = self._connection.execute(
            """
            SELECT *
            FROM candidate_frontier_history
            WHERE project_id = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_candidate_frontier(row) for row in cursor.fetchall()]

    def append_outbox_event(self, *, event_type, payload, message_id=None, created_at=None):
        return self._outbox.append_event(
            event_type=event_type,
            payload=payload,
            message_id=message_id,
            created_at=created_at,
        )

    def list_pending_outbox(
        self,
        *,
        event_type_prefix: str | None = None,
        exclude_event_type_prefix: str | None = None,
    ):
        return self._outbox.list_pending_filtered(
            event_type_prefix=event_type_prefix,
            exclude_event_type_prefix=exclude_event_type_prefix,
        )

    def list_outbox(self, *, limit: int = 50):
        return self._outbox.list_all(limit=limit)

    def mark_outbox_sent(self, message_id, *, sent_at=None):
        return self._outbox.mark_sent(message_id, sent_at=sent_at)

    def set_active_run(self, run_id: str | None) -> ProjectStatus:
        return self._update_status(active_run_id=run_id)

    def set_current_stage(self, stage: str | None) -> ProjectStatus:
        return self._update_status(current_stage=stage)

    def set_pending_command(self, command: str | None) -> ProjectStatus:
        return self._update_status(pending_command=command)

    def record_heartbeat(self, worker: WorkerName, timestamp=None) -> ProjectStatus:
        heartbeat_at = ensure_utc(timestamp or utc_now())
        if worker == "pipeline":
            return self._update_status(pipeline_heartbeat_at=heartbeat_at)
        if worker == "autoresearch":
            return self._update_status(autoresearch_heartbeat_at=heartbeat_at)
        raise ValueError(f"Unknown worker: {worker}")

    def clear_heartbeat(self, worker: WorkerName) -> ProjectStatus:
        if worker == "pipeline":
            return self._update_status(pipeline_heartbeat_at=None)
        if worker == "autoresearch":
            return self._update_status(autoresearch_heartbeat_at=None)
        raise ValueError(f"Unknown worker: {worker}")

    def set_candidate_revision(self, revision: str | None) -> ProjectStatus:
        return self._update_status(candidate_revision=revision)

    def set_baseline_revision(self, revision: str | None) -> ProjectStatus:
        return self._update_status(baseline_revision=revision)

    def set_recovery_marker(self, marker: str | None) -> ProjectStatus:
        return self._update_status(recovery_marker=marker)

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_status (
                    project_id TEXT PRIMARY KEY,
                    project_state TEXT NOT NULL,
                    pipeline_state TEXT NOT NULL,
                    autoresearch_state TEXT NOT NULL,
                    active_run_id TEXT,
                    current_stage TEXT,
                    pending_command TEXT,
                    pipeline_heartbeat_at TEXT,
                    autoresearch_heartbeat_at TEXT,
                    candidate_revision TEXT,
                    baseline_revision TEXT,
                    recovery_marker TEXT
                );

                CREATE TABLE IF NOT EXISTS command_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    source TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    accepted INTEGER NOT NULL,
                    project_state TEXT NOT NULL,
                    pipeline_state TEXT NOT NULL,
                    autoresearch_state TEXT NOT NULL,
                    pending_command TEXT,
                    message TEXT NOT NULL,
                    run_id TEXT
                );

                CREATE TABLE IF NOT EXISTS run_history (
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    PRIMARY KEY (project_id, run_id)
                );

                CREATE TABLE IF NOT EXISTS experiment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    candidate_revision TEXT NOT NULL,
                    baseline_revision TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    mutation_summary TEXT NOT NULL,
                    backtest_metrics_json TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    analysis_output_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_plan_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    hypothesis TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    plan_output_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    source_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    excerpt TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lesson_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    lesson_output_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS brain_note_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    note_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    generated INTEGER NOT NULL,
                    run_id TEXT,
                    iteration INTEGER,
                    revision TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, path)
                );

                CREATE TABLE IF NOT EXISTS trial_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    family TEXT NOT NULL,
                    artifact_kind TEXT NOT NULL,
                    candidate_revision TEXT NOT NULL,
                    baseline_revision TEXT NOT NULL,
                    compile_status TEXT NOT NULL,
                    falsification_pass INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS falsification_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    candidate_revision TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    checks_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lesson_graph_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    thesis TEXT NOT NULL,
                    mutation_delta TEXT NOT NULL,
                    observed_outcome TEXT NOT NULL,
                    failure_mode TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    novelty_score REAL NOT NULL,
                    knowledge_source_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS family_memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    family TEXT NOT NULL,
                    symbol_scope TEXT NOT NULL,
                    timeframe_scope TEXT NOT NULL,
                    regime_scope TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    linked_run_id TEXT NOT NULL,
                    linked_iteration INTEGER NOT NULL,
                    novelty_score REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS candidate_frontier_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    candidate_id TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    promoted INTEGER NOT NULL,
                    prescreen_reason TEXT NOT NULL,
                    prescreen_score REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outbox_messages (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                );
                """
            )
            self._ensure_run_history_updated_at_column()
            self._connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_command_history_project
                ON command_history (project_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_experiment_history_project
                ON experiment_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_analysis_history_project
                ON analysis_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_research_plan_history_project
                ON research_plan_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_knowledge_history_project
                ON knowledge_history (project_id, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_lesson_history_project
                ON lesson_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_brain_note_registry_project
                ON brain_note_registry (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_brain_note_registry_type
                ON brain_note_registry (project_id, note_type, updated_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_trial_history_project
                ON trial_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_falsification_history_project
                ON falsification_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_lesson_graph_history_project
                ON lesson_graph_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_family_memory_history_project
                ON family_memory_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_candidate_frontier_history_project
                ON candidate_frontier_history (project_id, updated_at DESC, created_at DESC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_candidate_frontier_history_iteration
                ON candidate_frontier_history (project_id, run_id, iteration, rank ASC, id DESC);

                CREATE INDEX IF NOT EXISTS idx_run_history_project_created
                ON run_history (project_id, created_at DESC, run_id DESC);

                CREATE INDEX IF NOT EXISTS idx_run_history_project_updated
                ON run_history (project_id, updated_at DESC, created_at DESC, run_id DESC);

                CREATE INDEX IF NOT EXISTS idx_outbox_pending
                ON outbox_messages (project_id, sent_at, event_type, created_at);
                """
            )

    def _ensure_run_history_updated_at_column(self) -> None:
        cursor = self._connection.execute("PRAGMA table_info(run_history)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "updated_at" in columns:
            self._connection.execute(
                """
                UPDATE run_history
                SET updated_at = COALESCE(updated_at, created_at)
                WHERE updated_at IS NULL
                """
            )
            return
        self._connection.execute(
            "ALTER TABLE run_history ADD COLUMN updated_at TEXT"
        )
        self._connection.execute(
            """
            UPDATE run_history
            SET updated_at = created_at
            WHERE updated_at IS NULL
            """
        )

    def _ensure_default_status(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO project_status (
                    project_id,
                    project_state,
                    pipeline_state,
                    autoresearch_state,
                    active_run_id,
                    current_stage,
                    pending_command,
                    pipeline_heartbeat_at,
                    autoresearch_heartbeat_at,
                    candidate_revision,
                    baseline_revision,
                    recovery_marker
                )
                VALUES (?, 'idle', 'idle', 'idle', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
                """,
                (self._project_id,),
            )

    def _update_status(self, **changes) -> ProjectStatus:
        if not changes:
            return self.get_status()

        normalized_changes: dict[str, Any] = {}
        for field, value in changes.items():
            if field in {"pipeline_heartbeat_at", "autoresearch_heartbeat_at"}:
                normalized_changes[field] = self._normalize_optional_datetime(value)
            else:
                normalized_changes[field] = value

        assignments = ", ".join(f"{field} = ?" for field in normalized_changes)
        values = [
            self._serialize_status_value(field, value)
            for field, value in normalized_changes.items()
        ]
        with self._connection:
            self._connection.execute(
                f"UPDATE project_status SET {assignments} WHERE project_id = ?",
                (*values, self._project_id),
            )
        return self.get_status()

    def _row_to_status(self, row: sqlite3.Row) -> ProjectStatus:
        return ProjectStatus(
            project_id=row["project_id"],
            project_state=row["project_state"],
            pipeline_state=row["pipeline_state"],
            autoresearch_state=row["autoresearch_state"],
            active_run_id=row["active_run_id"],
            current_stage=row["current_stage"],
            pending_command=row["pending_command"],
            pipeline_heartbeat_at=parse_datetime(row["pipeline_heartbeat_at"]),
            autoresearch_heartbeat_at=parse_datetime(row["autoresearch_heartbeat_at"]),
            candidate_revision=row["candidate_revision"],
            baseline_revision=row["baseline_revision"],
            recovery_marker=row["recovery_marker"],
        )

    def _row_to_command(self, row: sqlite3.Row) -> CommandRecord:
        requested_at = parse_datetime(row["requested_at"])
        if requested_at is None:
            raise ValueError("command_history.requested_at must not be null")
        return CommandRecord(
            id=row["id"],
            project_id=row["project_id"],
            command=row["command"],
            source=row["source"],
            requested_by=row["requested_by"],
            requested_at=requested_at,
            payload=self._deserialize_json(row["payload_json"]),
            accepted=bool(row["accepted"]),
            project_state=row["project_state"],
            pipeline_state=row["pipeline_state"],
            autoresearch_state=row["autoresearch_state"],
            pending_command=row["pending_command"],
            message=row["message"],
            run_id=row["run_id"],
        )

    def _row_to_experiment(self, row: sqlite3.Row) -> ExperimentRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("experiment_history timestamps must not be null")
        return ExperimentRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            candidate_revision=row["candidate_revision"],
            baseline_revision=row["baseline_revision"],
            hypothesis=row["hypothesis"],
            mutation_summary=row["mutation_summary"],
            backtest_metrics=self._deserialize_json(row["backtest_metrics_json"]),
            decision=row["decision"],
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_run(self, row: sqlite3.Row) -> RunRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"]) or created_at
        if created_at is None or updated_at is None:
            raise ValueError("run_history timestamps must not be null")
        return RunRecord(
            run_id=row["run_id"],
            project_id=row["project_id"],
            state=row["state"],
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_analysis(self, row: sqlite3.Row) -> AnalysisRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("analysis_history timestamps must not be null")
        return AnalysisRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            analysis_output=self._deserialize_json(row["analysis_output_json"]),
            summary=row["summary"],
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_research_plan(self, row: sqlite3.Row) -> ResearchPlanRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("research_plan_history timestamps must not be null")
        return ResearchPlanRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            hypothesis=row["hypothesis"],
            summary=row["summary"],
            plan_output=self._deserialize_json(row["plan_output_json"]),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_knowledge(self, row: sqlite3.Row) -> KnowledgeRecord:
        created_at = parse_datetime(row["created_at"])
        if created_at is None:
            raise ValueError("knowledge_history.created_at must not be null")
        return KnowledgeRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            source_path=row["source_path"],
            title=row["title"],
            excerpt=row["excerpt"],
            metadata=self._deserialize_json(row["metadata_json"]),
            created_at=created_at,
        )

    def _row_to_lesson(self, row: sqlite3.Row) -> LessonRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("lesson_history timestamps must not be null")
        return LessonRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            decision=row["decision"],
            summary=row["summary"],
            lesson_output=self._deserialize_json(row["lesson_output_json"]),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_brain_note(self, row: sqlite3.Row) -> BrainNoteRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("brain_note_registry timestamps must not be null")
        return BrainNoteRecord(
            id=row["id"],
            project_id=row["project_id"],
            note_type=row["note_type"],
            path=row["path"],
            title=row["title"],
            generated=bool(row["generated"]),
            run_id=row["run_id"],
            iteration=row["iteration"],
            revision=row["revision"],
            metadata=self._deserialize_json(row["metadata_json"]),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_trial(self, row: sqlite3.Row) -> TrialRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("trial_history timestamps must not be null")
        return TrialRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            family=row["family"],
            artifact_kind=row["artifact_kind"],
            candidate_revision=row["candidate_revision"],
            baseline_revision=row["baseline_revision"],
            compile_status=row["compile_status"],
            falsification_pass=bool(row["falsification_pass"]),
            decision=row["decision"],
            metadata=self._deserialize_json(row["metadata_json"]),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_falsification(self, row: sqlite3.Row) -> FalsificationRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("falsification_history timestamps must not be null")
        return FalsificationRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            candidate_revision=row["candidate_revision"],
            passed=bool(row["passed"]),
            checks=self._deserialize_json(row["checks_json"]),
            summary=row["summary"],
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_lesson_graph(self, row: sqlite3.Row) -> LessonGraphRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("lesson_graph_history timestamps must not be null")
        knowledge_source_ids = self._deserialize_json(row["knowledge_source_ids_json"]).get(
            "knowledge_source_ids",
            [],
        )
        return LessonGraphRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            decision=row["decision"],
            thesis=row["thesis"],
            mutation_delta=row["mutation_delta"],
            observed_outcome=row["observed_outcome"],
            failure_mode=row["failure_mode"],
            next_action=row["next_action"],
            confidence=row["confidence"],
            novelty_score=float(row["novelty_score"]),
            knowledge_source_ids=tuple(str(item) for item in knowledge_source_ids),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_family_memory(self, row: sqlite3.Row) -> FamilyMemoryRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("family_memory_history timestamps must not be null")
        return FamilyMemoryRecord(
            id=row["id"],
            project_id=row["project_id"],
            family=row["family"],
            symbol_scope=row["symbol_scope"],
            timeframe_scope=row["timeframe_scope"],
            regime_scope=row["regime_scope"],
            outcome=row["outcome"],
            linked_run_id=row["linked_run_id"],
            linked_iteration=row["linked_iteration"],
            novelty_score=float(row["novelty_score"]),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_candidate_frontier(self, row: sqlite3.Row) -> CandidateFrontierRecord:
        created_at = parse_datetime(row["created_at"])
        updated_at = parse_datetime(row["updated_at"])
        if created_at is None or updated_at is None:
            raise ValueError("candidate_frontier_history timestamps must not be null")
        return CandidateFrontierRecord(
            id=row["id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            iteration=row["iteration"],
            candidate_id=row["candidate_id"],
            rank=row["rank"],
            promoted=bool(row["promoted"]),
            prescreen_reason=row["prescreen_reason"],
            prescreen_score=float(row["prescreen_score"]),
            metadata=self._deserialize_json(row["metadata_json"]),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _serialize_json(self, payload: Mapping[str, Any]) -> str:
        return json.dumps(dict(payload), sort_keys=True)

    def _deserialize_json(self, payload_json: str) -> dict[str, Any]:
        value = json.loads(payload_json)
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object payload")
        return value

    def _normalize_optional_datetime(
        self,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)

    def _serialize_status_value(self, field: str, value: Any) -> Any:
        if field in {"pipeline_heartbeat_at", "autoresearch_heartbeat_at"}:
            return serialize_datetime(value)
        return value

    def _fetch_runs_for_ids(self, run_ids: set[str]) -> dict[str, RunRecord]:
        if not run_ids:
            return {}
        placeholders = ", ".join("?" for _ in run_ids)
        cursor = self._connection.execute(
            f"""
            SELECT run_id, project_id, state, created_at, updated_at
            FROM run_history
            WHERE project_id = ? AND run_id IN ({placeholders})
            """,
            (self._project_id, *sorted(run_ids)),
        )
        return {
            record.run_id: record
            for record in (self._row_to_run(row) for row in cursor.fetchall())
        }

    def _fetch_experiment_by_run_iteration(
        self,
        *,
        run_id: str,
        iteration: int,
    ) -> ExperimentRecord | None:
        cursor = self._connection.execute(
            """
            SELECT
                id,
                project_id,
                run_id,
                iteration,
                candidate_revision,
                baseline_revision,
                hypothesis,
                mutation_summary,
                backtest_metrics_json,
                decision,
                created_at,
                updated_at
            FROM experiment_history
            WHERE project_id = ? AND run_id = ? AND iteration = ?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (self._project_id, run_id, iteration),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_experiment(row)

    def _fetch_related_rows(
        self,
        *,
        table: str,
        row_factory,
        limit: int,
        iteration_keys: set[tuple[str, int]],
    ) -> dict[tuple[str, int], Any]:
        if not iteration_keys:
            return {}
        latest_ids: dict[tuple[str, int], int] = {}
        placeholders = ", ".join("(?, ?)" for _ in iteration_keys)
        parameters: list[Any] = [self._project_id]
        for run_id, iteration in sorted(iteration_keys):
            parameters.extend([run_id, iteration])
        cursor = self._connection.execute(
            f"""
            SELECT id, run_id, iteration
            FROM {table}
            WHERE project_id = ?
              AND (run_id, iteration) IN ({placeholders})
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (*parameters, limit * 4),
        )
        for row in cursor.fetchall():
            key = (row["run_id"], row["iteration"])
            latest_ids.setdefault(key, row["id"])
        if not latest_ids:
            return {}
        id_placeholders = ", ".join("?" for _ in latest_ids)
        row_cursor = self._connection.execute(
            f"""
            SELECT *
            FROM {table}
            WHERE project_id = ? AND id IN ({id_placeholders})
            """,
            (self._project_id, *latest_ids.values()),
        )
        return {
            (record.run_id, record.iteration): record
            for record in (row_factory(row) for row in row_cursor.fetchall())
        }

    def _fetch_family_memory_rows(
        self,
        *,
        limit: int,
        iteration_keys: set[tuple[str, int]],
    ) -> dict[tuple[str, int], FamilyMemoryRecord]:
        if not iteration_keys:
            return {}
        latest_ids: dict[tuple[str, int], int] = {}
        placeholders = ", ".join("(?, ?)" for _ in iteration_keys)
        parameters: list[Any] = [self._project_id]
        for run_id, iteration in sorted(iteration_keys):
            parameters.extend([run_id, iteration])
        cursor = self._connection.execute(
            f"""
            SELECT id, linked_run_id, linked_iteration
            FROM family_memory_history
            WHERE project_id = ?
              AND (linked_run_id, linked_iteration) IN ({placeholders})
            ORDER BY updated_at DESC, id DESC
            """,
            tuple(parameters),
        )
        for row in cursor.fetchall():
            key = (row["linked_run_id"], row["linked_iteration"])
            latest_ids.setdefault(key, row["id"])
        if not latest_ids:
            return {}
        id_placeholders = ", ".join("?" for _ in latest_ids)
        row_cursor = self._connection.execute(
            f"""
            SELECT *
            FROM family_memory_history
            WHERE project_id = ? AND id IN ({id_placeholders})
            LIMIT ?
            """,
            (self._project_id, *latest_ids.values(), limit),
        )
        return {
            (record.linked_run_id, record.linked_iteration): record
            for record in (self._row_to_family_memory(row) for row in row_cursor.fetchall())
        }

    def _fetch_frontier_rows(
        self,
        *,
        limit: int,
        iteration_keys: set[tuple[str, int]],
    ) -> dict[tuple[str, int], list[CandidateFrontierRecord]]:
        if not iteration_keys:
            return {}
        placeholders = ", ".join("(?, ?)" for _ in iteration_keys)
        parameters: list[Any] = [self._project_id]
        for run_id, iteration in sorted(iteration_keys):
            parameters.extend([run_id, iteration])
        cursor = self._connection.execute(
            f"""
            SELECT *
            FROM candidate_frontier_history
            WHERE project_id = ?
              AND (run_id, iteration) IN ({placeholders})
            ORDER BY rank ASC, updated_at DESC, id DESC
            LIMIT ?
            """,
            (*parameters, limit),
        )
        grouped: dict[tuple[str, int], list[CandidateFrontierRecord]] = {}
        for row in cursor.fetchall():
            record = self._row_to_candidate_frontier(row)
            grouped.setdefault((record.run_id, record.iteration), []).append(record)
        return grouped

    def _fetch_brain_notes_for_iterations(
        self,
        *,
        limit: int,
        iteration_keys: set[tuple[str, int]],
    ) -> dict[tuple[str, int], list[BrainNoteRecord]]:
        if not iteration_keys:
            return {}
        placeholders = ", ".join("(?, ?)" for _ in iteration_keys)
        parameters: list[Any] = [self._project_id]
        for run_id, iteration in sorted(iteration_keys):
            parameters.extend([run_id, iteration])
        cursor = self._connection.execute(
            f"""
            SELECT *
            FROM brain_note_registry
            WHERE project_id = ?
              AND (run_id, iteration) IN ({placeholders})
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (*parameters, limit),
        )
        grouped: dict[tuple[str, int], list[BrainNoteRecord]] = {}
        for row in cursor.fetchall():
            record = self._row_to_brain_note(row)
            grouped.setdefault((record.run_id, record.iteration), []).append(record)
        return grouped
