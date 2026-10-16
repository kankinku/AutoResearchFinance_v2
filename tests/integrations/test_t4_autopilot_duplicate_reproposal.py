"""T4 real checkpoint service with injected model proposals, no mock model success."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from application.academic_checkpoint_service import DuplicateAlgorithmPlanError
from research.llm.checkpoint_autopilot import (
    AcademicCheckpointAutopilot,
    DuplicateProposalRetryExceeded,
)
from tests.integrations.test_academic_autopilot import (
    TenGenerationScriptedProvider,
    _service,
)


class DuplicateThenNovel(TenGenerationScriptedProvider):
    def __init__(self, reject_attempts: int) -> None:
        super().__init__()
        self.reject_attempts = reject_attempts
        self.initial_plan: dict | None = None
        self.rejections: list[dict] = []
        self.gen_two_calls = 0

    def propose(self, context: dict) -> dict:
        if context.get("output_contract") != "AlgorithmPlan":
            return super().propose(context)
        if context["generation"] == 1:
            plan = super().propose(context)
            self.initial_plan = deepcopy(plan)
            return plan
        if context["generation"] == 2:
            self.gen_two_calls += 1
            if "candidate_rejection" in context:
                self.rejections.append(deepcopy(context["candidate_rejection"]))
            if self.gen_two_calls <= self.reject_attempts:
                assert self.initial_plan is not None
                duplicate = deepcopy(self.initial_plan)
                duplicate["plan_id"] = "duplicate_g2_" + str(self.gen_two_calls)
                return duplicate
        return super().propose(context)


def test_duplicate_is_reproposed_on_same_token_and_only_new_model_commits(
    tmp_path: Path,
) -> None:
    svc, sid = _service(tmp_path, generations=2)
    model = DuplicateThenNovel(1)
    result = AcademicCheckpointAutopilot(svc, model).run(sid, max_generations=2)
    state = svc.get({"session_id": sid})
    assert result["status"] == "COMPLETED"
    assert result["completed_generations"] == 2
    assert result["rejected_duplicate_proposals_this_call"] == 1
    assert result["external_model_proposals_this_call"] == 5
    assert model.gen_two_calls == 2
    assert model.rejections == [{
        "type": "DUPLICATE_ALGORITHM_PLAN",
        "code": "DUPLICATE_SEMANTIC_PLAN",
        "matching_prior_generation": 1,
        "reproposal_number": 1,
        "remaining_reproposals": 3,
        "required_change": model.rejections[0]["required_change"],
    }]
    assert "genuinely different" in model.rejections[0]["required_change"]
    assert len(state["history"]) == 2
    assert state["history"][0]["algorithm_plan"]["plan_id"] == model.initial_plan["plan_id"]
    assert state["history"][1]["algorithm_plan"]["plan_id"] != model.initial_plan["plan_id"]
    assert state["orders_enabled"] is False
    for i in (1, 2):
        s7 = svc.evaluate_experiments({"session_id": sid, "generation": i})
        assert s7["original_generation_evidence_hash"] == state["history"][i - 1]["evidence_hash"]


def test_duplicate_budget_exhausts_without_interrupting_or_claiming_generation(
    tmp_path: Path,
) -> None:
    svc, sid = _service(tmp_path, generations=2)
    model = DuplicateThenNovel(99)
    runner = AcademicCheckpointAutopilot(svc, model, max_duplicate_reproposals=3)
    initial = runner.run(sid, max_generations=1)
    original_hash = svc.get({"session_id": sid})["history"][0]["evidence_hash"]
    assert initial["completed_generations"] == 1
    with pytest.raises(DuplicateProposalRetryExceeded, match="retry budget exhausted"):
        runner.run(sid, max_generations=1)
    state = svc.get({"session_id": sid})
    assert model.gen_two_calls == 4
    assert state["completed_generations"] == 1
    assert state["history"][0]["evidence_hash"] == original_hash
    assert state["checkpoint_phase"] == "AWAITING_PLAN"
    assert state["status"] == "AWAITING_PROVIDER"
    assert state["error_type"] is None
    assert state["orders_enabled"] is False


def test_no_retry_when_model_or_other_service_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc, sid = _service(tmp_path, generations=1)
    model = DuplicateThenNovel(0)
    original = svc.submit_plan
    attempts = []

    def infrastructure_error(args: dict) -> dict:
        attempts.append(args["session_id"])
        raise RuntimeError("database disk failure")

    monkeypatch.setattr(svc, "submit_plan", infrastructure_error)
    with pytest.raises(RuntimeError, match="disk failure"):
        AcademicCheckpointAutopilot(svc, model).run(sid, max_generations=1)
    assert len(attempts) == 1
    assert svc.get({"session_id": sid})["completed_generations"] == 0
    monkeypatch.setattr(svc, "submit_plan", original)


def test_duplicate_error_is_typed_and_rejects_unsupported_error_label() -> None:
    exc = DuplicateAlgorithmPlanError("DUPLICATE_EFFECTIVE_SIGNALS", 11)
    assert exc.previous_generation == 11
    assert exc.code == "DUPLICATE_EFFECTIVE_SIGNALS"
    assert isinstance(exc, ValueError)
    with pytest.raises(ValueError, match="invalid duplicate"):
        DuplicateAlgorithmPlanError("AUTH_REQUIRED", 1)


def test_invalid_reproposal_budget_is_rejected(tmp_path: Path) -> None:
    svc, _ = _service(tmp_path, generations=1)
    for bad in (-1, 4, True, 1.5):
        with pytest.raises(ValueError, match="max_duplicate_reproposals"):
            AcademicCheckpointAutopilot(
                svc, DuplicateThenNovel(0), max_duplicate_reproposals=bad,
            )

def test_retry_budget_exhaustion_is_recorded_as_review_not_automatically_replayed(
    tmp_path: Path,
) -> None:
    import json

    from research.llm.safe_checkpoint_recovery import (
        RecoveryAction,
        ResearchReviewRequired,
        SafeCheckpointRecoveryController,
    )

    svc, sid = _service(tmp_path, generations=2)
    model = DuplicateThenNovel(99)
    log = tmp_path / "audit" / "recovery.jsonl"
    runner = AcademicCheckpointAutopilot(svc, model)
    with pytest.raises(ResearchReviewRequired) as caught:
        SafeCheckpointRecoveryController(
            runner, audit_path=log,
        ).run(sid, max_generations=2)
    assert caught.value.action == RecoveryAction.HOLD_DUPLICATE_BUDGET
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["decision"] == "HOLD_DUPLICATE_BUDGET"
    assert events[0]["completed_generations"] == 1
    assert events[0]["orders_enabled"] is False
    assert model.gen_two_calls == 4  # recovery controller did not restart model
    state = svc.get({"session_id": sid})
    assert state["checkpoint_phase"] == "AWAITING_PLAN"
    assert state["completed_generations"] == 1
