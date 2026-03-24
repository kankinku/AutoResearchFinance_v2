from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from finance_autoresearch.state.models import ProjectStatus

from .command_gate import NormalizedCommand


@dataclass(slots=True, frozen=True)
class SeedBaselineValidation:
    valid: bool
    message: str = "seed baseline validated"


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
) -> TransitionDecision:
    if command.command == "status":
        return _decision(True, status, "status retrieved")

    if command.command == "start_pipeline":
        if status.project_state not in {"idle", "degraded"}:
            return _reject(status, "start_pipeline is allowed only from idle or degraded")

        return _decision(
            True,
            replace(
                status,
                project_state="active",
                pipeline_state="running",
                pending_command=None,
            ),
            "pipeline started",
        )

    if command.command == "start_autoresearch":
        if status.autoresearch_state in {"running", "paused"} or status.active_run_id is not None:
            return _reject(status, "start_autoresearch is already active")

        if status.project_state != "idle" or status.pipeline_state != "success":
            return _reject(
                status,
                "start_autoresearch requires an idle project with a successful pipeline",
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
            "autoresearch started",
            run_id=run_id,
            record_run_state="running",
        )

    if command.command == "pause_autoresearch":
        if status.autoresearch_state != "running":
            return _reject(status, "pause_autoresearch is allowed only while autoresearch is running")

        return _decision(
            True,
            replace(status, project_state="paused", autoresearch_state="paused"),
            "autoresearch paused",
        )

    if command.command == "resume_autoresearch":
        if status.project_state != "paused" or status.autoresearch_state != "paused":
            return _reject(
                status,
                "resume_autoresearch requires a paused project and paused autoresearch",
            )

        return _decision(
            True,
            replace(status, project_state="active", autoresearch_state="running"),
            "autoresearch resumed",
        )

    if command.command == "stop_autoresearch":
        if status.autoresearch_state not in {"running", "paused"}:
            return _reject(
                status,
                "stop_autoresearch is allowed only while autoresearch is running or paused",
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
                "autoresearch stopped",
                run_id=None,
            )

        return _decision(
            True,
            replace(status, pending_command="stop_autoresearch"),
            "stop_autoresearch queued for the next stage boundary",
        )

    if command.command == "reset_project":
        if status.project_state not in {"idle", "degraded"}:
            return _reject(status, "reset_project is allowed only from idle or degraded")

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
            "project reset",
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
