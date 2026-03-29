from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer
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


def normalize_command(
    raw_command: object,
    *,
    localizer: OutputLocalizer | None = None,
) -> NormalizedCommand:
    resolved_localizer = localizer or DEFAULT_LOCALIZER
    if not isinstance(raw_command, Mapping):
        raise CommandValidationError(
            resolved_localizer.log("command.invalid_payload_mapping")
        )
    raw_command = dict(raw_command)

    command = _require_command(raw_command.get("command"), localizer=resolved_localizer)
    project_id = _require_project_id(raw_command.get("project_id"), localizer=resolved_localizer)
    source = _require_source(raw_command.get("source"), localizer=resolved_localizer)
    requested_by = _require_requested_by(
        raw_command.get("requested_by"),
        localizer=resolved_localizer,
    )
    requested_at = _require_requested_at(
        raw_command.get("requested_at"),
        localizer=resolved_localizer,
    )
    payload = _require_payload(raw_command.get("payload"), localizer=resolved_localizer)

    return NormalizedCommand(
        command=command,
        project_id=project_id,
        source=source,
        requested_by=requested_by,
        requested_at=requested_at,
        payload=payload,
        requested_at_value=ensure_utc(datetime.fromisoformat(requested_at)),
    )


def _require_command(
    value: object,
    *,
    localizer: OutputLocalizer,
) -> SupervisorCommand:
    if not isinstance(value, str) or value not in ALLOWED_COMMANDS:
        allowed = ", ".join(ALLOWED_COMMANDS)
        raise CommandValidationError(
            localizer.log("command.invalid_command", allowed=allowed)
        )
    return value


def _require_project_id(
    value: object,
    *,
    localizer: OutputLocalizer,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CommandValidationError(localizer.log("command.invalid_project_id"))
    return value


def _require_source(
    value: object,
    *,
    localizer: OutputLocalizer,
) -> CommandSource:
    if not isinstance(value, str) or value not in ALLOWED_SOURCES:
        allowed = ", ".join(ALLOWED_SOURCES)
        raise CommandValidationError(
            localizer.log("command.invalid_source", allowed=allowed)
        )
    return value


def _require_requested_by(
    value: object,
    *,
    localizer: OutputLocalizer,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommandValidationError(localizer.log("command.invalid_requested_by"))
    return value


def _require_requested_at(
    value: object,
    *,
    localizer: OutputLocalizer,
) -> str:
    if not isinstance(value, str):
        raise CommandValidationError(localizer.log("command.invalid_requested_at"))

    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise CommandValidationError(localizer.log("command.invalid_requested_at")) from exc
    return value


def _require_payload(
    value: object,
    *,
    localizer: OutputLocalizer,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CommandValidationError(localizer.log("command.invalid_payload"))
    return dict(value)
