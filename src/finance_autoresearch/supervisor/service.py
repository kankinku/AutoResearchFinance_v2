from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from uuid import uuid4

from finance_autoresearch.state.repository import StateRepository

from .command_gate import CommandValidationError, NormalizedCommand, normalize_command
from .process_lock import ProcessLock
from .transition_guard import (
    SeedBaselineValidation,
    TransitionDecision,
    evaluate_transition,
)

SeedValidator = Callable[[str | None], bool | tuple[bool, str] | SeedBaselineValidation]


class SupervisorService:
    def __init__(
        self,
        *,
        state_store: StateRepository,
        seed_validator: SeedValidator | None = None,
        run_id_factory: Callable[[], str] | None = None,
        process_lock: ProcessLock | None = None,
    ) -> None:
        self._state_store = state_store
        self._seed_validator = seed_validator
        self._run_id_factory = run_id_factory or (lambda: str(uuid4()))
        self._process_lock = process_lock or ProcessLock.for_state_store(state_store)

    def handle(self, raw_command: Mapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
        with self._process_lock:
            status = self._state_store.get_status()
            try:
                command = normalize_command(raw_command)
            except CommandValidationError as exc:
                return self._build_response(
                    accepted=False,
                    status=status,
                    message=str(exc),
                    run_id=status.active_run_id,
                )

            if command.project_id not in {None, status.project_id}:
                decision = TransitionDecision(
                    accepted=False,
                    status=status,
                    message="command project_id does not match the supervisor store",
                    run_id=status.active_run_id,
                )
            else:
                decision = evaluate_transition(
                    command,
                    status,
                    run_id_factory=self._run_id_factory,
                    seed_validation_factory=lambda: self._seed_validation_for(command),
                )

            self._apply_status(status, decision.status)
            if decision.record_run_state is not None and decision.run_id is not None:
                self._state_store.record_run(
                    run_id=decision.run_id,
                    state=decision.record_run_state,
                )
            self._state_store.record_command(
                command.command,
                source=command.source,
                requested_by=command.requested_by,
                requested_at=command.requested_at_value,
                payload=command.payload,
                accepted=decision.accepted,
                project_state=decision.status.project_state,
                pipeline_state=decision.status.pipeline_state,
                autoresearch_state=decision.status.autoresearch_state,
                pending_command=decision.status.pending_command,
                message=decision.message,
                run_id=decision.run_id,
            )
            return self._build_response(
                accepted=decision.accepted,
                status=decision.status,
                message=decision.message,
                run_id=decision.run_id,
            )

    def _seed_validation_for(
        self,
        command: NormalizedCommand,
    ) -> SeedBaselineValidation | None:
        if command.command != "start_autoresearch":
            return None

        if self._seed_validator is None:
            return SeedBaselineValidation(
                valid=False,
                message="seed validator is not configured",
            )

        result = self._seed_validator(command.project_id)
        if isinstance(result, SeedBaselineValidation):
            return result
        if isinstance(result, tuple):
            valid, message = result
            return SeedBaselineValidation(valid=bool(valid), message=message)
        return SeedBaselineValidation(valid=bool(result))

    def _apply_status(self, current_status, next_status) -> None:
        if (
            current_status.project_state != next_status.project_state
            or current_status.pipeline_state != next_status.pipeline_state
            or current_status.autoresearch_state != next_status.autoresearch_state
        ):
            self._state_store.set_status(
                project_state=next_status.project_state,
                pipeline_state=next_status.pipeline_state,
                autoresearch_state=next_status.autoresearch_state,
            )
        if current_status.active_run_id != next_status.active_run_id:
            self._state_store.set_active_run(next_status.active_run_id)
        if current_status.current_stage != next_status.current_stage:
            self._state_store.set_current_stage(next_status.current_stage)
        if current_status.pending_command != next_status.pending_command:
            self._state_store.set_pending_command(next_status.pending_command)
        if current_status.pipeline_heartbeat_at != next_status.pipeline_heartbeat_at:
            if next_status.pipeline_heartbeat_at is None:
                self._state_store.clear_heartbeat("pipeline")
            else:
                self._state_store.record_heartbeat(
                    "pipeline",
                    next_status.pipeline_heartbeat_at,
                )
        if current_status.autoresearch_heartbeat_at != next_status.autoresearch_heartbeat_at:
            if next_status.autoresearch_heartbeat_at is None:
                self._state_store.clear_heartbeat("autoresearch")
            else:
                self._state_store.record_heartbeat(
                    "autoresearch",
                    next_status.autoresearch_heartbeat_at,
                )
        if current_status.candidate_revision != next_status.candidate_revision:
            self._state_store.set_candidate_revision(next_status.candidate_revision)
        if current_status.baseline_revision != next_status.baseline_revision:
            self._state_store.set_baseline_revision(next_status.baseline_revision)
        if current_status.recovery_marker != next_status.recovery_marker:
            self._state_store.set_recovery_marker(next_status.recovery_marker)

    def _build_response(
        self,
        *,
        accepted: bool,
        status,
        message: str,
        run_id: str | None,
    ) -> dict[str, Any]:
        return {
            "accepted": accepted,
            "project_state": status.project_state,
            "pipeline_state": status.pipeline_state,
            "autoresearch_state": status.autoresearch_state,
            "pending_command": status.pending_command,
            "message": message,
            "run_id": run_id,
        }
