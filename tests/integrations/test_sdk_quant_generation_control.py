"""SDK orchestration must not fabricate a GPT turn or a committed generation."""

from __future__ import annotations

from copy import deepcopy

import pytest

from application.sdk_quant_generation_control import (
    BlockedHostDispatch,
    UnsafeCheckpoint,
    analyze_checkpoint,
    run_sdk_generation_loop,
)

SID = "a" * 32


def snapshot(*, completed: int = 1, requested: int = 3, phase: str = "AWAITING_PLAN") -> dict:
    return {
        "session_id": SID,
        "completed_generations": completed,
        "requested_generations": requested,
        "checkpoint_phase": phase,
        "status": "COMPLETED" if completed == requested else "AWAITING_PROVIDER",
        "checkpoint_token": "token-123" if completed < requested else None,
        "model_context": {"context_hash": "context-a"} if completed < requested else None,
        "history": [
            {"generation": i, "evidence_hash": f"{i:064x}"} for i in range(1, completed + 1)
        ],
        "orders_enabled": False,
        "independent_oos_approved": False,
        "dataset_hash": "b" * 64,
        "final_report": {
            "all_proposed_hypotheses_measured": True,
            "gateway_s7_count_source": "HASH_VERIFIED_IMMUTABLE_GATEWAY_REPORTS",
        },
    }


class Service:
    def __init__(self, state: dict):
        self.state = state
        self.calls = 0

    def get(self, args: dict) -> dict:
        assert args == {"session_id": SID}
        self.calls += 1
        return deepcopy(self.state)


class FixtureHost:
    """Test-double, NOT a real ChatGPT model or an independently verified host."""

    fixture_only = True

    def __init__(self, service: Service, *, fail: bool = False):
        self.service = service
        self.calls = 0
        self.fail = fail

    def dispatch(self, request: dict) -> None:
        self.calls += 1
        if self.fail:
            raise ConnectionError("lost response")
        state = self.service.state
        if request["checkpoint_phase"] == "AWAITING_PLAN":
            state["checkpoint_phase"] = "AWAITING_DIAGNOSIS"
            state["checkpoint_token"] = "diagnosis-token"
        else:
            state["completed_generations"] += 1
            state["history"].append(
                {
                    "generation": state["completed_generations"],
                    "evidence_hash": f"{state['completed_generations']:064x}",
                }
            )
            if state["completed_generations"] == state["requested_generations"]:
                state["status"] = "COMPLETED"
                state["checkpoint_phase"] = "COMPLETED"
                state["checkpoint_token"] = None
            else:
                state["checkpoint_phase"] = "AWAITING_PLAN"
                state["checkpoint_token"] = "next-plan-token"


def test_no_model_host_means_no_work_and_no_fabricated_generations():
    service = Service(snapshot())
    result = run_sdk_generation_loop(service, session_id=SID, target=3, host=None)
    assert result["status"] == "BLOCKED_MODEL_HOST_DISPATCH"
    assert result["new_generations"] == 0
    assert service.state["completed_generations"] == 1
    assert service.calls == 1


def test_fixture_two_stages_count_only_committed_completed_generations():
    service = Service(snapshot())
    host = FixtureHost(service)
    result = run_sdk_generation_loop(
        service, session_id=SID, target=2, host=host, fixture_mode=True, max_dispatches=2
    )
    assert result["status"] == "TARGET_REACHED_TEST_ONLY"
    assert result["new_generations"] == 1
    assert result["official_verified_generations"] == 0
    assert host.calls == 2
    assert result["model_provenance"] == "TEST_ONLY_NO_PROVIDER_ATTESTATION"


def test_budget_stops_before_counting_partial_plan():
    service = Service(snapshot())
    host = FixtureHost(service)
    result = run_sdk_generation_loop(
        service, session_id=SID, target=3, host=host, fixture_mode=True, max_dispatches=1
    )
    assert result["status"] == "DISPATCH_BUDGET_EXHAUSTED"
    assert result["new_generations"] == 0
    assert service.state["checkpoint_phase"] == "AWAITING_DIAGNOSIS"


def test_uncertain_host_failure_never_autoretries():
    service = Service(snapshot())
    host = FixtureHost(service, fail=True)
    with pytest.raises(BlockedHostDispatch, match="reconcile"):
        run_sdk_generation_loop(
            service, session_id=SID, target=3, host=host, fixture_mode=True, max_dispatches=20
        )
    assert host.calls == 1
    assert service.state["completed_generations"] == 1


def test_nonfixture_unknown_host_denied_even_with_callback():
    service = Service(snapshot())
    with pytest.raises(BlockedHostDispatch, match="not authenticated"):
        run_sdk_generation_loop(
            service, session_id=SID, target=3, host=FixtureHost(service), fixture_mode=False
        )
    assert service.state["completed_generations"] == 1


def test_changes_to_oos_order_session_dataset_and_evidence_fail_closed():
    for key, value in [
        ("orders_enabled", True),
        ("independent_oos_approved", True),
        ("session_id", "x" * 32),
        ("dataset_hash", None),
    ]:
        state = snapshot()
        state[key] = value
        with pytest.raises(UnsafeCheckpoint):
            analyze_checkpoint(state, expected_session=SID)
    state = snapshot()
    state["history"][0]["evidence_hash"] = "bad"
    with pytest.raises(UnsafeCheckpoint):
        analyze_checkpoint(state, expected_session=SID)


def test_stale_phase_or_fake_generation_jump_is_rejected():
    state = snapshot(completed=3, requested=3, phase="COMPLETED")
    result = run_sdk_generation_loop(Service(state), session_id=SID, target=3, host=None)
    assert result["status"] == "TARGET_REACHED"
    assert result["new_generations"] == 0
    service = Service(snapshot())

    class Malicious(FixtureHost):
        def dispatch(self, request: dict) -> None:
            self.calls += 1
            self.service.state["completed_generations"] += 2
            self.service.state["history"].extend(
                [
                    {"generation": 2, "evidence_hash": f"{2:064x}"},
                    {"generation": 3, "evidence_hash": f"{3:064x}"},
                ]
            )
            self.service.state["checkpoint_phase"] = "COMPLETED"
            self.service.state["status"] = "COMPLETED"

    with pytest.raises(UnsafeCheckpoint, match="generation jump"):
        run_sdk_generation_loop(
            service, session_id=SID, target=3, host=Malicious(service), fixture_mode=True
        )


def test_generation_commit_without_s7_is_blocked():
    service = Service(snapshot())

    class MissingS7(FixtureHost):
        def dispatch(self, request: dict) -> None:
            super().dispatch(request)
            if request["checkpoint_phase"] == "AWAITING_DIAGNOSIS":
                self.service.state["final_report"]["all_proposed_hypotheses_measured"] = False

    with pytest.raises(UnsafeCheckpoint, match="S7"):
        run_sdk_generation_loop(
            service, session_id=SID, target=2, host=MissingS7(service), fixture_mode=True
        )


def test_existing_generation_head_rewrite_is_blocked():
    service = Service(snapshot())

    class Tampering(FixtureHost):
        def dispatch(self, request: dict) -> None:
            super().dispatch(request)
            self.service.state["history"][0]["evidence_hash"] = "c" * 64

    with pytest.raises(UnsafeCheckpoint, match="existing evidence"):
        run_sdk_generation_loop(
            service, session_id=SID, target=2, host=Tampering(service), fixture_mode=True
        )
