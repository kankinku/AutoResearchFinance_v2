from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import uuid4

from .models import (
    OutboxMessage,
    ensure_utc,
    parse_datetime,
    serialize_datetime,
    utc_now,
)


class SQLiteOutbox:
    def __init__(self, connection: sqlite3.Connection, project_id: str) -> None:
        self._connection = connection
        self._project_id = project_id

    def append_event(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        message_id: str | None = None,
        created_at: datetime | None = None,
    ) -> OutboxMessage:
        created = ensure_utc(created_at or utc_now())
        event = OutboxMessage(
            id=message_id or uuid4().hex,
            project_id=self._project_id,
            event_type=event_type,
            payload=dict(payload),
            created_at=created,
            sent_at=None,
        )

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO outbox_messages (
                    id,
                    project_id,
                    event_type,
                    payload_json,
                    created_at,
                    sent_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.project_id,
                    event.event_type,
                    json.dumps(event.payload),
                    serialize_datetime(event.created_at),
                    None,
                ),
            )

        return event

    def list_pending(self) -> list[OutboxMessage]:
        return self.list_pending_filtered()

    def list_pending_filtered(
        self,
        *,
        event_type_prefix: str | None = None,
        exclude_event_type_prefix: str | None = None,
    ) -> list[OutboxMessage]:
        clauses = ["project_id = ?", "sent_at IS NULL"]
        parameters: list[str] = [self._project_id]
        if event_type_prefix is not None:
            clauses.append("event_type LIKE ?")
            parameters.append(f"{event_type_prefix}%")
        if exclude_event_type_prefix is not None:
            clauses.append("event_type NOT LIKE ?")
            parameters.append(f"{exclude_event_type_prefix}%")
        cursor = self._connection.execute(
            f"""
            SELECT id, project_id, event_type, payload_json, created_at, sent_at
            FROM outbox_messages
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at ASC, rowid ASC
            """,
            tuple(parameters),
        )
        return [self._row_to_message(row) for row in cursor.fetchall()]

    def list_all(self, *, limit: int = 50) -> list[OutboxMessage]:
        cursor = self._connection.execute(
            """
            SELECT id, project_id, event_type, payload_json, created_at, sent_at
            FROM outbox_messages
            WHERE project_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (self._project_id, limit),
        )
        return [self._row_to_message(row) for row in cursor.fetchall()]

    def mark_sent(
        self,
        message_id: str,
        *,
        sent_at: datetime | None = None,
    ) -> OutboxMessage:
        delivered_at = ensure_utc(sent_at or utc_now())

        with self._connection:
            self._connection.execute(
                """
                UPDATE outbox_messages
                SET sent_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (serialize_datetime(delivered_at), message_id, self._project_id),
            )

        cursor = self._connection.execute(
            """
            SELECT id, project_id, event_type, payload_json, created_at, sent_at
            FROM outbox_messages
            WHERE id = ? AND project_id = ?
            """,
            (message_id, self._project_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Unknown outbox message: {message_id}")
        return self._row_to_message(row)

    def _row_to_message(self, row: sqlite3.Row) -> OutboxMessage:
        return OutboxMessage(
            id=row["id"],
            project_id=row["project_id"],
            event_type=row["event_type"],
            payload=json.loads(row["payload_json"]),
            created_at=parse_datetime(row["created_at"]) or utc_now(),
            sent_at=parse_datetime(row["sent_at"]),
        )
