from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from finance_autoresearch.state.models import CommandSource, ensure_utc

SupervisorCommand = Literal[
    "start_pipeline",
    "start_autoresearch",
    "pause_autoresearch",
    "resume_autoresearch",
    "stop_autoresearch",
    "reset_project",
    "status",
]

ALLOWED_COMMANDS: tuple[SupervisorCommand, ...] = (
    "start_pipeline",
    "start_autoresearch",
    "pause_autoresearch",
    "resume_autoresearch",
    "stop_autoresearch",
    "reset_project",
    "status",
)
ALLOWED_SOURCES: tuple[CommandSource, ...] = (
    "cli",
    "telegram_control",
    "openclaw",
    "dashboard",
)


class CommandValidationError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class NormalizedCommand:
    command: SupervisorCommand
    project_id: str | None
    source: CommandSource
    requested_by: str
    requested_at: str
    payload: dict[str, Any]
    requested_at_value: datetime


def normalize_command(raw_command: object) -> NormalizedCommand:
    if not isinstance(raw_command, Mapping):
        raise CommandValidationError("invalid command: expected an object payload")
    raw_command = dict(raw_command)

    command = _require_command(raw_command.get("command"))
    project_id = _require_project_id(raw_command.get("project_id"))
    source = _require_source(raw_command.get("source"))
    requested_by = _require_requested_by(raw_command.get("requested_by"))
    requested_at = _require_requested_at(raw_command.get("requested_at"))
    payload = _require_payload(raw_command.get("payload"))

    return NormalizedCommand(
        command=command,
        project_id=project_id,
        source=source,
        requested_by=requested_by,
        requested_at=requested_at,
        payload=payload,
        requested_at_value=ensure_utc(datetime.fromisoformat(requested_at)),
    )


def _require_command(value: object) -> SupervisorCommand:
    if not isinstance(value, str) or value not in ALLOWED_COMMANDS:
        allowed = ", ".join(ALLOWED_COMMANDS)
        raise CommandValidationError(
            f"invalid command: command must be one of {{{allowed}}}"
        )
    return value


def _require_project_id(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CommandValidationError("invalid command: project_id must be a string or null")
    return value


def _require_source(value: object) -> CommandSource:
    if not isinstance(value, str) or value not in ALLOWED_SOURCES:
        allowed = ", ".join(ALLOWED_SOURCES)
        raise CommandValidationError(
            f"invalid command: source must be one of {{{allowed}}}"
        )
    return value


def _require_requested_by(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommandValidationError("invalid command: requested_by must be a non-empty string")
    return value


def _require_requested_at(value: object) -> str:
    if not isinstance(value, str):
        raise CommandValidationError("invalid command: requested_at must be an ISO datetime string")

    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise CommandValidationError(
            "invalid command: requested_at must be an ISO datetime string"
        ) from exc
    return value


def _require_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CommandValidationError("invalid command: payload must be an object")
    return dict(value)
