"""T4 checkpoint orchestration tests use fabricated responses; never model provenance."""

from __future__ import annotations

from copy import deepcopy

import pytest

from application.t4_checkpoint_orchestrator import (
    ModelUnavailable,
    run_checkpoint_loop,
)


class FakeCheckpoint:
    """In-memory protocol double; even 100/100 is TEST_ONLY, not a real GPT study."""

    def __init__(self, count: int = 20, target: int = 100):
        self.completed = count
        self.target = target
        self.phase = "AWAITING_PLAN"
        self.token_serial = 10
        self.plan_calls = 0
        self.diagnosis_calls = 0
        self.lost_reply_on_plan = False
        self.lost_reply_on_diagnosis = False
        self.fail_plan_once = False
        self.fail_diagnosis_once = False
        self.seen_plan: set[str] = set()
        self.seen_diagnosis: set[str] = set()
        self.replay_calls = 0
        self.plan_token_history: list[str] = []
        self.diagnosis_token_history: list[str] = []

    @property
    def token(self) -> str:
        return f"checkpoint-token-{self.token_serial}"

    def get(self, args):
        assert args["session_id"] == "1" * 32
        phase = self.phase if self.completed < self.target else "COMPLETED"
        return {
            "session_id": args["session_id"],
            "completed_generations": self.completed,
            "requested_generations": self.target,
            "checkpoint_phase": phase,
            "checkpoint_token": self.token,
            "model_context": {
                "generation": self.completed + 1,
                "output_contract": "InheritedResearchIntent",
                "schema": "study-context",
                "counted_parent_inheritance_ready": True,
            },
            "orders_enabled": False,
            "independent_oos_approved": False,
            "p4_s7_quality_audit": {"approved_count": self.completed},
            "model_capture_audit": {"independent_model_invocation_verified": False},
        }

    def submit_plan(self, args):
        if args["checkpoint_token"] in self.seen_plan:
            self.replay_calls += 1
            return self.get({"session_id": args["session_id"]})
        self.plan_calls += 1
        self.plan_token_history.append(args["checkpoint_token"])
        assert self.phase == "AWAITING_PLAN" and args["checkpoint_token"] == self.token
        assert args["require_execution_change"] is True
        if self.fail_plan_once:
            self.fail_plan_once = False
            raise ValueError("UNCHANGED_CANONICAL_FILLS: no new orders")
        self.seen_plan.add(args["checkpoint_token"])
        self.phase = "AWAITING_DIAGNOSIS"
        self.token_serial += 1
        if self.lost_reply_on_plan:
            self.lost_reply_on_plan = False
            raise ConnectionError("reply lost after commit")
        return self.get({"session_id": args["session_id"]})

    def submit_diagnosis(self, args):
        if args["checkpoint_token"] in self.seen_diagnosis:
            self.replay_calls += 1
            return self.get({"session_id": args["session_id"]})
        self.diagnosis_calls += 1
        self.diagnosis_token_history.append(args["checkpoint_token"])
        assert self.phase == "AWAITING_DIAGNOSIS" and args["checkpoint_token"] == self.token
        if self.fail_diagnosis_once:
            self.fail_diagnosis_once = False
            raise ValueError("P4_S7_QUALITY_REJECTED: NO_OBSERVED_EFFECT")
        self.seen_diagnosis.add(args["checkpoint_token"])
        self.completed += 1
        self.phase = "AWAITING_PLAN"
        self.token_serial += 1
        if self.lost_reply_on_diagnosis:
            self.lost_reply_on_diagnosis = False
            raise ConnectionError("reply lost after commit")
        return self.get({"session_id": args["session_id"]})


class FakeModel:
    def __init__(self):
        self.calls = []
        self.fail_once = False

    def propose(self, context):
        self.calls.append(deepcopy(context))
        if self.fail_once:
            self.fail_once = False
            raise ConnectionError("provider unreachable")
        return {"mode": "structure", "reason": "fixture only"}


def _loop(svc, model, **opts):
    return run_checkpoint_loop(
        svc,
        session_id="1" * 32,
        model=model,
        target_generations=svc.target,
        mode="TEST_ONLY",
        **opts,
    )


def test_eighty_generation_run_does_not_pause_after_ten():
    svc, model = FakeCheckpoint(), FakeModel()
    report = _loop(svc, model)
    assert report["status"] == "TARGET_REACHED"
    assert report["initial_generations"] == 20 and report["completed_generations"] == 100
    assert report["new_generations"] == 80
    assert report["model_calls"] == 160
    assert svc.plan_calls == svc.diagnosis_calls == 80
    assert len(svc.plan_token_history) == len(set(svc.plan_token_history)) == 80
    assert report["real_provider_verified"] is False
    assert report["mode"] == "TEST_ONLY"


def test_lost_replies_do_not_repeat_the_committed_action():
    svc = FakeCheckpoint(target=22)
    svc.lost_reply_on_plan = True
    svc.lost_reply_on_diagnosis = True
    report = _loop(svc, FakeModel())
    assert report["completed_generations"] == 22
    assert svc.plan_calls == 2 and svc.diagnosis_calls == 2
    assert report["recovered_reply_losses"] == 2


def test_same_token_feedback_and_bounded_rejection():
    svc, model = FakeCheckpoint(target=21), FakeModel()
    svc.fail_plan_once = True
    svc.fail_diagnosis_once = True
    report = _loop(svc, model, max_retries_per_checkpoint=2)
    assert report["completed_generations"] == 21
    assert svc.plan_calls == 2 and svc.diagnosis_calls == 2
    assert svc.plan_token_history[0] == svc.plan_token_history[1]
    assert svc.diagnosis_token_history[0] == svc.diagnosis_token_history[1]
    assert sum("research_loop_feedback" in c for c in model.calls) == 2


def test_provider_failure_stops_safely_and_resumes():
    svc, model = FakeCheckpoint(target=22), FakeModel()
    model.fail_once = True
    with pytest.raises(ModelUnavailable):
        _loop(svc, model)
    assert svc.completed == 20 and svc.plan_calls == 0
    report = _loop(svc, model)
    assert report["completed_generations"] == 22


def test_budget_stop_and_reentry_preserve_authoritative_generation():
    svc, model = FakeCheckpoint(target=24), FakeModel()
    first = _loop(svc, model, max_model_calls=3)
    assert first["status"] == "MODEL_CALL_BUDGET_REACHED"
    assert first["completed_generations"] == 21
    assert svc.phase == "AWAITING_DIAGNOSIS"
    second = _loop(svc, model)
    assert second["status"] == "TARGET_REACHED"
    assert second["completed_generations"] == 24
    assert svc.plan_calls == svc.diagnosis_calls == 4


def test_no_model_is_fail_closed_before_mutation():
    svc = FakeCheckpoint(target=21)
    with pytest.raises(ModelUnavailable, match="authenticated"):
        _loop(svc, None)
    assert svc.completed == 20 and not svc.plan_calls


def test_quality_and_trading_boundaries_cannot_be_disabled():
    svc = FakeCheckpoint(target=21)
    svc.get = lambda args: {**FakeCheckpoint(target=21).get(args), "orders_enabled": True}
    with pytest.raises(ValueError, match="order"):
        _loop(svc, FakeModel())
    assert svc.plan_calls == 0


def test_retry_exhaustion_returns_blocked_not_fake_generations():
    svc, model = FakeCheckpoint(target=21), FakeModel()

    def always_reject(args):
        svc.plan_calls += 1
        raise ValueError("UNCHANGED_CANONICAL_FILLS: no new orders")

    svc.submit_plan = always_reject
    report = _loop(svc, model, max_retries_per_checkpoint=2)
    assert report["status"] == "RETRY_EXHAUSTED"
    assert report["completed_generations"] == 20
    assert svc.plan_calls == 3
    assert report["real_provider_verified"] is False


def test_real_isolated_service_checkpoint_completes_only_after_s7(tmp_path):
    """Actual canonical service, fixture decisions and fixture market, NOT live GPT."""
    from tests.integrations.test_quant_p4_s7_precommit import _svc
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher

    service = _svc(tmp_path)
    started = service.start({"data_path": "data/study.parquet", "generations": 1})

    class LabOnlyModel:
        def propose(self, context):
            payload = ScriptedResearcher().propose(context)
            if context.get("schema") != "research-diagnostic-context-v1":
                return payload
            hypothesis = payload["hypotheses"][0]
            hypothesis["hypothesis_id"] = "bounded_position_size_s7_fixture"
            hypothesis["expected_metric"] = "max_drawdown"
            hypothesis["predicted_direction"] = "DECREASE"
            hypothesis["test_design"] = "PARAMETER"
            hypothesis["next_intent"] = {
                "mode": "parameter",
                "parent_ids": hypothesis["next_intent"]["parent_ids"],
                "operations": [
                    {
                        "op": "CHANGE_POSITION_SIZE",
                        "path": "risk.position_size_pct",
                        "value": 70.0,
                    }
                ],
                "rationale": "Fixture-only 70-percent sizing control.",
            }
            return payload

    report = run_checkpoint_loop(
        service,
        session_id=started["session_id"],
        model=LabOnlyModel(),
        mode="TEST_ONLY",
    )
    state = service.get({"session_id": started["session_id"]})
    assert state["completed_generations"] == 1
    assert state["checkpoint_phase"] == "COMPLETED"
    assert state["p4_s7_quality_audit"]["approved_count"] == 1
    assert report["model_calls"] == 2
    assert report["real_provider_verified"] is False
