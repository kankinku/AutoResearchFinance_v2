from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    AnalysisRecord,
    CommandRecord,
    ExperimentRecord,
    ProjectStatus,
    RunRecord,
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
        self._db_path = db_path
        self._project_id = project_id
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
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
    ) -> RunRecord:
        created_timestamp = ensure_utc(created_at or utc_now())
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO run_history (
                    run_id,
                    project_id,
                    state,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    self._project_id,
                    state,
                    serialize_datetime(created_timestamp),
                ),
            )
        return RunRecord(
            run_id=run_id,
            project_id=self._project_id,
            state=state,
            created_at=created_timestamp,
        )

    def get_latest_run(self) -> RunRecord | None:
        cursor = self._connection.execute(
            """
            SELECT run_id, project_id, state, created_at
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
        messages = self._outbox.list_pending()
        if event_type_prefix is not None:
            messages = [
                message for message in messages if message.event_type.startswith(event_type_prefix)
            ]
        if exclude_event_type_prefix is not None:
            messages = [
                message
                for message in messages
                if not message.event_type.startswith(exclude_event_type_prefix)
            ]
        return messages

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

                CREATE TABLE IF NOT EXISTS outbox_messages (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_command_history_project
                ON command_history (project_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_experiment_history_project
                ON experiment_history (project_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_analysis_history_project
                ON analysis_history (project_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_outbox_pending
                ON outbox_messages (project_id, sent_at, created_at);
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
        if created_at is None:
            raise ValueError("run_history.created_at must not be null")
        return RunRecord(
            run_id=row["run_id"],
            project_id=row["project_id"],
            state=row["state"],
            created_at=created_at,
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
