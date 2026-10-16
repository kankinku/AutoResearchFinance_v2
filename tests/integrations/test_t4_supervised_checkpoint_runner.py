"""Local-only T4 single-owner, pause/resume, heartbeat; scripted model, never real orders."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from research.llm.supervised_checkpoint_runner import (
    ResearchRunSupervisor,
    SupervisorStateError,
)
from runtime.lifecycle_lock import LifecycleBusyError
from tests.integrations.test_academic_autopilot import _service
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _init(tmp_path: Path, count: int = 2):
    svc, sid = _service(tmp_path, generations=count)
    owner = ResearchRunSupervisor(tmp_path / "local-control")
    log = tmp_path / "local-control" / "recovery.jsonl"
    return svc, sid, owner, log


def test_foreground_supervised_runner_proves_evidence_and_status(tmp_path: Path) -> None:
    svc, sid, owner, log = _init(tmp_path)
    provider = ScriptedResearcher()
    first = owner.run(
        sid,
        service=svc,
        provider=provider,
        max_generations=1,
        audit_path=log,
        heartbeat_interval=0.1,
    )
    state = svc.get({"session_id": sid})
    assert first["advanced_generations_this_call"] == 1
    assert first["supervisor_state"] == "AWAITING_PROVIDER"
    assert state["completed_generations"] == 1
    assert state["orders_enabled"] is False
    assert (
        svc.evaluate_experiments(
            {
                "session_id": sid,
                "generation": 1,
            }
        )["original_generation_evidence_hash"]
        == state["history"][0]["evidence_hash"]
    )
    reported = owner.status(sid)
    assert reported["requested_action"] == "RUN"
    assert reported["last_recorded"]["completed_generations"] == 1
    assert reported["last_recorded"]["last_evidence_hash"] == state["history"][0]["evidence_hash"]
    assert reported["last_recorded"]["provider_source"] == "EXPLICIT_CALLER_SUPPLIED_ONLY"

    second = owner.run(
        sid,
        service=svc,
        provider=provider,
        max_generations=1,
        audit_path=log,
        heartbeat_interval=0.1,
    )
    assert second["supervisor_state"] == "COMPLETED"
    assert svc.get({"session_id": sid})["completed_generations"] == 2
    assert (
        svc.get({"session_id": sid})["history"][0]["evidence_hash"]
        == state["history"][0]["evidence_hash"]
    )


def test_pause_during_model_call_returns_without_submitting_it(tmp_path: Path) -> None:
    svc, sid, owner, log = _init(tmp_path)
    delegate = ScriptedResearcher()

    class PauseDuringProvider:
        def propose(self, context):
            reply = delegate.propose(context)
            owner.request(sid, "PAUSE")
            return reply

    result = owner.run(
        sid,
        service=svc,
        provider=PauseDuringProvider(),
        max_generations=1,
        audit_path=log,
        heartbeat_interval=0.1,
    )
    assert result["supervisor_state"] == "PAUSED"
    state = svc.get({"session_id": sid})
    assert state["completed_generations"] == 0
    assert state["checkpoint_phase"] == "AWAITING_PLAN"
    assert owner.status(sid)["requested_action"] == "PAUSE"

    with pytest.raises(SupervisorStateError, match="explicit RESUME"):
        owner.run(sid, service=svc, provider=delegate, max_generations=1, audit_path=log)
    owner.request(sid, "RUN")  # explicit intent only; never starts a worker
    assert svc.get({"session_id": sid})["completed_generations"] == 0
    resumed = owner.run(sid, service=svc, provider=delegate, max_generations=1, audit_path=log)
    assert resumed["advanced_generations_this_call"] == 1


def test_stop_before_diagnosis_preserves_staged_plan_for_resume(tmp_path: Path) -> None:
    svc, sid, owner, log = _init(tmp_path)
    delegate = ScriptedResearcher()

    class StopBeforeDiagnosis:
        def propose(self, context):
            if context.get("schema") == "research-diagnostic-context-v1":
                owner.request(sid, "STOP")
            return delegate.propose(context)

    result = owner.run(
        sid,
        service=svc,
        provider=StopBeforeDiagnosis(),
        max_generations=1,
        audit_path=log,
        heartbeat_interval=0.1,
    )
    assert result["supervisor_state"] == "STOPPED"
    staged = svc.get({"session_id": sid})
    assert staged["checkpoint_phase"] == "AWAITING_DIAGNOSIS"
    assert staged["completed_generations"] == 0
    token = staged["checkpoint_token"]
    owner.request(sid, "RUN")
    result2 = owner.run(
        sid,
        service=svc,
        provider=delegate,
        max_generations=1,
        audit_path=log,
        heartbeat_interval=0.1,
    )
    assert result2["advanced_generations_this_call"] == 1
    final = svc.get({"session_id": sid})
    assert final["completed_generations"] == 1
    assert final["history"][0]["generation"] == 1
    assert final["checkpoint_token"] != token


def test_owner_lock_rejects_overlapping_runner_and_heartbeat_updates(
    tmp_path: Path,
) -> None:
    svc, sid, owner, log = _init(tmp_path)
    delegate = ScriptedResearcher()
    waiting, release = threading.Event(), threading.Event()
    outcomes = []

    class BlockingProvider:
        def propose(self, context):
            waiting.set()
            assert release.wait(10), "test provider timeout"
            return delegate.propose(context)

    def run_bg():
        try:
            outcomes.append(
                owner.run(
                    sid,
                    service=svc,
                    provider=BlockingProvider(),
                    max_generations=1,
                    audit_path=log,
                    heartbeat_interval=0.1,
                )
            )
        except Exception as exc:
            outcomes.append(exc)

    thread = threading.Thread(target=run_bg)
    thread.start()
    try:
        assert waiting.wait(5)
        first = owner.status(sid)["last_recorded"]["heartbeat_at_utc"]
        time.sleep(0.3)
        other = owner.status(sid)
        assert other["last_recorded"]["heartbeat_at_utc"] != first
        assert other["last_recorded"]["supervisor_state"] == "RUNNING"
        with pytest.raises(LifecycleBusyError):
            owner.run(sid, service=svc, provider=delegate, max_generations=1, audit_path=log)
        assert svc.get({"session_id": sid})["completed_generations"] == 0
    finally:
        release.set()
        thread.join(timeout=15)
    assert not thread.is_alive()
    assert len(outcomes) == 1 and isinstance(outcomes[0], dict)
    assert outcomes[0]["advanced_generations_this_call"] == 1


def test_no_model_no_run_and_bad_control_does_not_modify_session(tmp_path: Path) -> None:
    svc, sid, owner, log = _init(tmp_path)
    with pytest.raises(SupervisorStateError, match="external model provider"):
        owner.run(sid, service=svc, provider=object(), max_generations=1, audit_path=log)
    with pytest.raises(SupervisorStateError, match="invalid research session"):
        owner.request("../escape", "PAUSE")
    with pytest.raises(SupervisorStateError, match="must be RUN/PAUSE/STOP"):
        owner.request(sid, "APPROVE_POLICY_BYPASS")
    with pytest.raises(SupervisorStateError, match="max_generations"):
        owner.run(
            sid, service=svc, provider=ScriptedResearcher(), max_generations=0, audit_path=log
        )
    assert svc.get({"session_id": sid})["completed_generations"] == 0
    assert svc.get({"session_id": sid})["orders_enabled"] is False


def test_supervisor_control_file_rejects_symlink(tmp_path: Path) -> None:
    root = tmp_path / "control"
    owner = ResearchRunSupervisor(root)
    sid = "1" * 32
    target = tmp_path / "target"
    target.write_text('{"desired":"RUN"}')
    (root / (sid + ".request.json")).symlink_to(target)
    with pytest.raises(SupervisorStateError, match="symlink"):
        owner.requested_action(sid)


def test_stale_heartbeat_never_claims_worker_is_running(tmp_path: Path) -> None:
    _, sid, owner, _ = _init(tmp_path)
    owner._save(
        owner._path(sid, "status.json"),
        {
            "session_id": sid,
            "supervisor_state": "RUNNING",
            "heartbeat_at_utc": "2020-01-01T00:00:00+00:00",
            "heartbeat_interval_seconds": 1,
        },
    )
    snapshot = owner.status(sid)
    assert snapshot["heartbeat_health"] == "STALE_OR_UNVERIFIED"
    assert snapshot["requires_live_worker_confirmation"] is True

    # Request RESUME never claims a new live owner or starts GPT.
    owner.request(sid, "RUN")
    assert owner.status(sid)["heartbeat_health"] == "STALE_OR_UNVERIFIED"


def test_bounded_model_proposals_stop_before_diagnosis_and_preserve_checkpoint(
    tmp_path: Path,
) -> None:
    svc, sid, owner, log = _init(tmp_path)
    delegate = ScriptedResearcher()

    class CountingProvider:
        def __init__(self):
            self.count = 0

        def propose(self, context):
            self.count += 1
            return delegate.propose(context)

    provider = CountingProvider()
    result = owner.run(
        sid, service=svc, provider=provider, max_generations=2,
        max_model_proposals=1, audit_path=log,
    )
    state = svc.get({'session_id': sid})
    assert result['supervisor_state'] == 'PAUSED'
    assert result['pause_reason'] == 'MODEL_PROPOSAL_BUDGET_REACHED'
    assert result['model_proposals_used'] == 1
    assert provider.count == 1
    assert state['completed_generations'] == 0
    assert state['checkpoint_phase'] == 'AWAITING_DIAGNOSIS'
    staged_token = state['checkpoint_token']
    assert owner.status(sid)['last_recorded']['checkpoint_phase'] == 'AWAITING_DIAGNOSIS'
    assert owner.status(sid)['last_recorded']['provider_source'] == 'EXPLICIT_CALLER_SUPPLIED_ONLY'

    continued = owner.run(
        sid, service=svc, provider=provider, max_generations=1,
        max_model_proposals=1, audit_path=log,
    )
    assert continued['supervisor_state'] == 'AWAITING_PROVIDER'
    assert provider.count == 2
    assert svc.get({'session_id': sid})['completed_generations'] == 1
    assert svc.get({'session_id': sid})['checkpoint_token'] != staged_token


def test_model_proposal_budget_validation_refuses_before_model_call(tmp_path: Path) -> None:
    svc, sid, owner, log = _init(tmp_path)

    class ForbiddenProvider:
        def propose(self, context):
            raise AssertionError('invalid budget must never call model')

    for bad in (0, -1, True, 1001):
        with pytest.raises(SupervisorStateError, match='model proposal budget'):
            owner.run(
                sid, service=svc, provider=ForbiddenProvider(),
                max_generations=1, max_model_proposals=bad, audit_path=log,
            )
    assert svc.get({'session_id': sid})['completed_generations'] == 0
