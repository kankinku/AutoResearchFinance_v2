from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import typer

from finance_autoresearch.supervisor.service import SupervisorService


COMMANDS: tuple[str, ...] = (
    "status",
    "start_pipeline",
    "start_autoresearch",
    "pause_autoresearch",
    "resume_autoresearch",
    "stop_autoresearch",
    "reset_project",
)


def build_command_payload(
    *,
    command: str,
    source: str,
    requested_by: str,
    project_id: str | None,
    payload: dict[str, Any] | None = None,
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "command": command,
        "project_id": project_id,
        "source": source,
        "requested_by": requested_by,
        "requested_at": (
            requested_at or datetime.now(timezone.utc)
        ).isoformat(),
        "payload": dict(payload or {}),
    }


def dispatch_command(
    *,
    supervisor: SupervisorService,
    command: str,
    source: str,
    requested_by: str,
    project_id: str | None,
    payload: dict[str, Any] | None = None,
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    return supervisor.handle(
        build_command_payload(
            command=command,
            source=source,
            requested_by=requested_by,
            project_id=project_id,
            payload=payload,
            requested_at=requested_at,
        )
    )


def emit_response(response: dict[str, Any]) -> None:
    typer.echo(json.dumps(response, sort_keys=True))
