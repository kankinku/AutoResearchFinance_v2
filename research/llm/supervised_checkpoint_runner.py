"""Operator-controlled foreground research supervision, not a model provider.

One local session owner, cooperative pause/stop before each model call, and
an atomic heartbeat/status file. Never starts GPT without an explicit provider.
No detached workers, trading orders, OAuth changes or automatic policy bypass.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from research.llm.checkpoint_autopilot import (
    AcademicCheckpointAutopilot,
    AutonomousTransport,
    OperatorPauseRequested,
)
from research.llm.safe_checkpoint_recovery import ResearchReviewRequired
from runtime.lifecycle_lock import lifecycle_lock

_SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
_DESIRED = frozenset({"RUN", "PAUSE", "STOP"})
_STATES = frozenset(
    {
        "IDLE",
        "RUNNING",
        "PAUSED",
        "STOPPED",
        "COMPLETED",
        "AWAITING_PROVIDER",
        "REVIEW_REQUIRED",
    }
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupervisorStateError(RuntimeError):
    """Fail closed on damaged state or invalid control input."""


class ResearchRunSupervisor:
    """Per-session locked, explicit foreground supervisor for existing MCP research."""

    def __init__(self, control_dir: Path) -> None:
        self.directory = control_dir.resolve()
        if control_dir.is_symlink():
            raise SupervisorStateError("control directory symlink not allowed")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.directory.is_symlink() or stat.S_IMODE(self.directory.stat().st_mode) & 0o077:
            raise SupervisorStateError("control directory must be owner-only (0700)")
        self._write_lock = threading.RLock()

    def _path(self, session_id: str, suffix: str) -> Path:
        if not _SESSION_RE.fullmatch(session_id):
            raise SupervisorStateError("invalid research session ID")
        return self.directory / f"{session_id}.{suffix}"

    def _load(self, path: Path) -> dict[str, Any] | None:
        if path.is_symlink():
            raise SupervisorStateError("supervisor control file symlink not allowed")
        if not path.exists():
            return None
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise SupervisorStateError("supervisor control must be owner-only (0600)")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise SupervisorStateError("malformed supervisor state") from exc
        if not isinstance(data, dict):
            raise SupervisorStateError("supervisor state must be an object")
        return data

    def _save(self, path: Path, data: dict[str, Any]) -> None:
        with self._write_lock:
            if path.is_symlink():
                raise SupervisorStateError("supervisor state symlink not allowed")
            tmp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, sort_keys=True, ensure_ascii=False)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)

    def requested_action(self, session_id: str) -> str:
        obj = self._load(self._path(session_id, "request.json"))
        if obj is None:
            return "RUN"
        if obj.get("session_id") != session_id or obj.get("desired") not in _DESIRED:
            raise SupervisorStateError("invalid supervisor request")
        return str(obj["desired"])

    def request(self, session_id: str, desired: str) -> dict[str, Any]:
        """Requested PAUSE/STOP/RESUME never starts a model call by itself."""
        if desired not in _DESIRED:
            raise SupervisorStateError("desired action must be RUN/PAUSE/STOP")
        self.requested_action(session_id)
        data = {
            "session_id": session_id,
            "desired": desired,
            "requested_at_utc": _timestamp(),
            "source": "explicit_operator_request",
        }
        self._save(self._path(session_id, "request.json"), data)
        return data

    def status(self, session_id: str) -> dict[str, Any]:
        record = self._load(self._path(session_id, "status.json"))
        heartbeat_health = "NOT_RUNNING"
        if record is not None and record.get("supervisor_state") == "RUNNING":
            heartbeat_health = "STALE_OR_UNVERIFIED"
            try:
                timestamp = datetime.fromisoformat(record["heartbeat_at_utc"])
                age = (datetime.now(timezone.utc) - timestamp).total_seconds()
                interval = float(record.get("heartbeat_interval_seconds", 2.0))
                if timestamp.tzinfo is not None and 0 <= age <= max(5.0, interval * 3):
                    # Recent heartbeat is not proof that a provider/runner will
                    # make forward progress or that this PID is still its owner.
                    heartbeat_health = "RECENT_UNVERIFIED"
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
        return {
            "session_id": session_id,
            "requested_action": self.requested_action(session_id),
            "last_recorded": record,
            "heartbeat_health": heartbeat_health,
            "requires_live_worker_confirmation": True,
            "orders_enabled": False,
        }

    def _snapshot(
        self,
        session_id: str,
        service: AcademicMCPCheckpointService,
        *,
        state: str,
        owner: str,
        failure: str | None = None,
    ) -> dict[str, Any]:
        record = service.get({"session_id": session_id})
        if (
            record["orders_enabled"] is not False
            or record["independent_oos_approved"] is not False
            or record["session_id"] != session_id
            or len(record["history"]) != record["completed_generations"]
        ):
            raise SupervisorStateError("untrusted research checkpoint")
        return {
            "session_id": session_id,
            "supervisor_state": state,
            "owner_pid": os.getpid(),
            "owner_nonce": owner,
            "heartbeat_at_utc": _timestamp(),
            "checkpoint_phase": record["checkpoint_phase"],
            "completed_generations": record["completed_generations"],
            "requested_generations": record["requested_generations"],
            "last_evidence_hash": (
                record["history"][-1]["evidence_hash"] if record["history"] else None
            ),
            "last_failure_class": failure,
            "orders_enabled": False,
            "independent_oos_approved": False,
            "provider_source": "EXPLICIT_CALLER_SUPPLIED_ONLY",
        }

    def run(
        self,
        session_id: str,
        *,
        service: AcademicMCPCheckpointService,
        provider: AutonomousTransport,
        max_generations: int,
        audit_path: Path,
        heartbeat_interval: float = 1.0,
        max_model_proposals: int | None = None,
    ) -> dict[str, Any]:
        if type(max_generations) is not int or not 1 <= max_generations <= 100:
            raise SupervisorStateError("max_generations must be 1..100")
        if not 0.1 <= heartbeat_interval <= 30:
            raise SupervisorStateError("heartbeat interval must be 0.1..30 seconds")
        if max_model_proposals is None:
            max_model_proposals = max_generations * 5
        if (type(max_model_proposals) is not int
                or not 1 <= max_model_proposals <= 1000):
            raise SupervisorStateError("model proposal budget must be 1..1000")
        if not callable(getattr(provider, "propose", None)):
            raise SupervisorStateError("explicit external model provider required")
        proposal_limit: int = int(max_model_proposals)
        model_proposals_used = 0
        model_budget_hit = False
        stop_beat = threading.Event()
        owner = secrets.token_hex(12)
        with lifecycle_lock(self._path(session_id, "owner.lock")):
            if self.requested_action(session_id) != "RUN":
                raise SupervisorStateError("operator PAUSE/STOP active: explicit RESUME required")
            original = self._snapshot(session_id, service, state="RUNNING", owner=owner)
            if original["checkpoint_phase"] not in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
                raise SupervisorStateError("research checkpoint not ready for foreground run")
            original["heartbeat_interval_seconds"] = heartbeat_interval
            self._save(self._path(session_id, "status.json"), original)

            # Only the owner may publish heartbeat. During a blocking model
            # request this proves process liveness, NOT generation progress.
            def heartbeat() -> None:
                while not stop_beat.wait(heartbeat_interval):
                    with self._write_lock:
                        try:
                            stored = self._load(self._path(session_id, "status.json"))
                            if stored is None or stored.get("owner_nonce") != owner:
                                return
                            stored["heartbeat_at_utc"] = _timestamp()
                            self._save(self._path(session_id, "status.json"), stored)
                        except (OSError, SupervisorStateError):
                            return

            beat = threading.Thread(target=heartbeat, daemon=True)
            beat.start()
            supervisor = self

            class GuardedProvider:
                def propose(self, context: dict[str, Any]) -> dict[str, Any]:
                    nonlocal model_proposals_used, model_budget_hit
                    action = supervisor.requested_action(session_id)
                    if action != "RUN":
                        raise OperatorPauseRequested(f"operator requested {action}")
                    if model_proposals_used >= proposal_limit:
                        model_budget_hit = True
                        raise OperatorPauseRequested("model proposal budget reached")
                    model_proposals_used += 1
                    reply = provider.propose(context)
                    # A stop that arrives during a blocking model call must
                    # prevent submitting the newly returned uncommitted plan.
                    after = supervisor.requested_action(session_id)
                    if after != "RUN":
                        raise OperatorPauseRequested(f"operator requested {after}")
                    if not isinstance(reply, dict):
                        raise SupervisorStateError("model response must be a structured object")
                    return reply

            try:
                run_result = AcademicCheckpointAutopilot(
                    service,
                    GuardedProvider(),
                ).run_resumable(
                    session_id,
                    max_generations=max_generations,
                    audit_path=audit_path,
                )
            except OperatorPauseRequested:
                if model_budget_hit:
                    self._save(
                        self._path(session_id, "status.json"),
                        self._snapshot(session_id, service, state="PAUSED", owner=owner),
                    )
                    return {
                        "supervisor_state": "PAUSED",
                        "pause_reason": "MODEL_PROPOSAL_BUDGET_REACHED",
                        "model_proposals_used": model_proposals_used,
                        "max_model_proposals": proposal_limit,
                        **self.status(session_id),
                    }
                action = self.requested_action(session_id)
                final_state = "STOPPED" if action == "STOP" else "PAUSED"
                self._save(
                    self._path(session_id, "status.json"),
                    self._snapshot(session_id, service, state=final_state, owner=owner),
                )
                return {"supervisor_state": final_state, **self.status(session_id)}
            except Exception as exc:
                failure = (
                    "ResearchReviewRequired"
                    if isinstance(exc, ResearchReviewRequired)
                    else type(exc).__name__
                )
                self._save(
                    self._path(session_id, "status.json"),
                    self._snapshot(
                        session_id, service, state="REVIEW_REQUIRED", owner=owner, failure=failure
                    ),
                )
                raise
            else:
                updated = self._snapshot(
                    session_id, service, state="AWAITING_PROVIDER", owner=owner
                )
                if updated["completed_generations"] == updated["requested_generations"]:
                    updated["supervisor_state"] = "COMPLETED"
                elif self.requested_action(session_id) != "RUN":
                    updated["supervisor_state"] = (
                        "STOPPED" if self.requested_action(session_id) == "STOP" else "PAUSED"
                    )
                self._save(self._path(session_id, "status.json"), updated)
                return {"supervisor_state": updated["supervisor_state"], **run_result}
            finally:
                stop_beat.set()
                beat.join(timeout=heartbeat_interval + 2)
