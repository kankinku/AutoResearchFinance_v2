from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from finance_autoresearch.localization import DEFAULT_LOCALIZER, OutputLocalizer
from finance_autoresearch.state.models import ProjectStatus

from .command_gate import NormalizedCommand


@dataclass(slots=True, frozen=True)
class SeedBaselineValidation:
    valid: bool
    message: str = DEFAULT_LOCALIZER.log("seed.validated")


@dataclass(slots=True, frozen=True)
class TransitionDecision:
    accepted: bool
    status: ProjectStatus
    message: str
    run_id: str | None
    record_run_state: str | None = None


def evaluate_transition(
    command: NormalizedCommand,
    status: ProjectStatus,
    *,
    run_id_factory: Callable[[], str],
    seed_validation_factory: Callable[[], SeedBaselineValidation] | None = None,
    localizer: OutputLocalizer | None = None,
) -> TransitionDecision:
    resolved_localizer = localizer or DEFAULT_LOCALIZER
    if command.command == "status":
        return _decision(True, status, resolved_localizer.log("transition.status_retrieved"))

    if command.command == "start_pipeline":
        if status.project_state not in {"idle", "degraded"}:
            return _reject(
                status,
                resolved_localizer.log("transition.start_pipeline_denied"),
            )

        return _decision(
            True,
            replace(
                status,
                project_state="active",
                pipeline_state="running",
                pending_command=None,
            ),
            resolved_localizer.log("transition.pipeline_started"),
        )

    if command.command == "start_autoresearch":
        if status.autoresearch_state in {"running", "paused"} or status.active_run_id is not None:
            return _reject(
                status,
                resolved_localizer.log("transition.start_autoresearch_active"),
            )

        if status.project_state != "idle" or status.pipeline_state != "success":
            return _reject(
                status,
                resolved_localizer.log("transition.start_autoresearch_requires_pipeline"),
            )

        validation = (
            seed_validation_factory()
            if seed_validation_factory is not None
            else SeedBaselineValidation(valid=True)
        )
        if not validation.valid:
            return _decision(
                False,
                replace(
                    status,
                    project_state="degraded",
                    autoresearch_state="failed",
                    pending_command=None,
                ),
                validation.message,
                run_id=None,
            )

        run_id = run_id_factory()
        return _decision(
            True,
            replace(
                status,
                project_state="active",
                autoresearch_state="running",
                active_run_id=run_id,
                current_stage=None,
                pending_command=None,
            ),
            resolved_localizer.log("transition.autoresearch_started"),
            run_id=run_id,
            record_run_state="running",
        )

    if command.command == "pause_autoresearch":
        if status.autoresearch_state != "running":
            return _reject(
                status,
                resolved_localizer.log("transition.pause_denied"),
            )

        return _decision(
            True,
            replace(status, project_state="paused", autoresearch_state="paused"),
            resolved_localizer.log("transition.autoresearch_paused"),
        )

    if command.command == "resume_autoresearch":
        if status.project_state != "paused" or status.autoresearch_state != "paused":
            return _reject(
                status,
                resolved_localizer.log("transition.resume_denied"),
            )

        return _decision(
            True,
            replace(status, project_state="active", autoresearch_state="running"),
            resolved_localizer.log("transition.autoresearch_resumed"),
        )

    if command.command == "stop_autoresearch":
        if status.autoresearch_state not in {"running", "paused"}:
            return _reject(
                status,
                resolved_localizer.log("transition.stop_denied"),
            )

        if status.autoresearch_state == "paused":
            return _decision(
                True,
                replace(
                    status,
                    project_state="idle",
                    autoresearch_state="success",
                    active_run_id=None,
                    current_stage=None,
                    pending_command=None,
                ),
                resolved_localizer.log("transition.autoresearch_stopped"),
                run_id=None,
            )

        return _decision(
            True,
            replace(status, pending_command="stop_autoresearch"),
            resolved_localizer.log("transition.stop_queued"),
        )

    if command.command == "reset_project":
        if status.project_state not in {"idle", "degraded"}:
            return _reject(
                status,
                resolved_localizer.log("transition.reset_denied"),
            )

        return _decision(
            True,
            replace(
                status,
                project_state="idle",
                pipeline_state="idle",
                autoresearch_state="idle",
                active_run_id=None,
                current_stage=None,
                pending_command=None,
                pipeline_heartbeat_at=None,
                autoresearch_heartbeat_at=None,
                candidate_revision=None,
                recovery_marker=None,
            ),
            resolved_localizer.log("transition.project_reset"),
            run_id=None,
        )

    raise ValueError(f"Unhandled command: {command.command}")


def _decision(
    accepted: bool,
    status: ProjectStatus,
    message: str,
    *,
    run_id: str | None | object = ...,
    record_run_state: str | None = None,
) -> TransitionDecision:
    resolved_run_id = status.active_run_id if run_id is ... else run_id
    return TransitionDecision(
        accepted=accepted,
        status=status,
        message=message,
        run_id=resolved_run_id,
        record_run_state=record_run_state,
    )


def _reject(status: ProjectStatus, message: str) -> TransitionDecision:
    return _decision(False, status, message)
