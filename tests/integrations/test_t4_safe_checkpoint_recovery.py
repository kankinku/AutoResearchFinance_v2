"""T4 bounded checkpoint recovery: injected failures, never a mock success claim."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.llm.checkpoint_autopilot import AcademicCheckpointAutopilot
from research.llm.safe_checkpoint_recovery import (
    ProviderPolicyRefusal,
    RecoveryAction,
    ResearchReviewRequired,
    SafeCheckpointRecoveryController,
    TransientProviderFailure,
    classify_research_failure,
)
from tests.integrations.test_academic_autopilot import (
    TenGenerationScriptedProvider,
    _service,
)
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


class FaultyProvider:
    def __init__(self, fail: list[BaseException]) -> None:
        self.fail = fail
        self.calls = 0
        self.plans = 0
        self.diagnostics = 0

    def propose(self, context: dict) -> dict:
        self.calls += 1
        if context.get("output_contract") == "AlgorithmPlan":
            self.plans += 1
        else:
            self.diagnostics += 1
        if self.fail:
            failure = self.fail.pop(0)
            raise failure
        return ScriptedResearcher().propose(context)


def _resume(
    tmp_path: Path, provider: FaultyProvider, **kwargs: object,
) -> tuple[dict, Path, str]:
    svc, sid = _service(tmp_path, generations=2)
    path = tmp_path / "recover" / "audit.jsonl"
    report = SafeCheckpointRecoveryController(
        AcademicCheckpointAutopilot(svc, provider),
        audit_path=path,
        pause=lambda _: None,
        **kwargs,
    ).run(sid, max_generations=2)
    return report, path, sid


def test_transient_provider_failure_at_plan_retries_without_duplicate(tmp_path: Path) -> None:
    model = FaultyProvider([TransientProviderFailure("network dropped")])
    report, journal, sid = _resume(tmp_path, model)
    assert report["session_id"] == sid
    assert report["status"] == "COMPLETED"
    assert report["completed_generations"] == 2
    assert report["advanced_generations_this_call"] == 2
    assert model.plans == 3  # First attempt failed, then two valid plans.
    assert model.diagnostics == 2
    logs = [json.loads(x) for x in journal.read_text().splitlines()]
    assert [x["decision"] for x in logs] == ["RETRY_TRANSIENT"]
    assert all(x["orders_enabled"] is False for x in logs)
    assert all("token" not in x for x in logs)


def test_transient_diagnosis_failure_resumes_saved_plan(tmp_path: Path) -> None:
    # Explicit custom provider: first plan works, first diagnosis loses transport.
    class FailFirstDiagnosis(FaultyProvider):
        def propose(self, context: dict) -> dict:
            if context.get("output_contract") != "AlgorithmPlan" and self.diagnostics == 0:
                self.diagnostics += 1
                raise TransientProviderFailure("timeout")
            return super().propose(context)

    model = FailFirstDiagnosis([])
    report, journal, _ = _resume(tmp_path, model)
    assert report["completed_generations"] == 2
    assert model.plans == 2  # Did not propose the first plan again.
    assert model.diagnostics == 3
    assert json.loads(journal.read_text().splitlines()[0])["decision"] == "RETRY_TRANSIENT"


def test_policy_refusal_holds_without_replaying(tmp_path: Path) -> None:
    svc, sid = _service(tmp_path, generations=2)
    model = FaultyProvider([ProviderPolicyRefusal("policy denied")])
    path = tmp_path / "audits" / "review.jsonl"
    recovery = SafeCheckpointRecoveryController(
        AcademicCheckpointAutopilot(svc, model), audit_path=path,
    )
    with pytest.raises(ResearchReviewRequired) as caught:
        recovery.run(sid, max_generations=2)
    assert caught.value.action == RecoveryAction.HOLD_POLICY
    assert model.calls == 1
    assert svc.get({"session_id": sid})["completed_generations"] == 0
    assert svc.get({"session_id": sid})["checkpoint_phase"] == "AWAITING_PLAN"
    report = json.loads(path.read_text().splitlines()[0])
    assert report["decision"] == "HOLD_POLICY"
    assert report["host_policy_override"] is False


def test_generic_unknown_failure_holds_default(tmp_path: Path) -> None:
    svc, sid = _service(tmp_path, generations=2)
    model = FaultyProvider([RuntimeError("unexpected backend")])
    recovery = SafeCheckpointRecoveryController(
        AcademicCheckpointAutopilot(svc, model),
        audit_path=tmp_path / "review.jsonl",
    )
    with pytest.raises(ResearchReviewRequired) as caught:
        recovery.run(sid, max_generations=2)
    assert caught.value.action == RecoveryAction.HOLD_UNKNOWN
    assert model.calls == 1
    assert svc.get({"session_id": sid})["completed_generations"] == 0


def test_transport_retry_limit_does_not_loop(tmp_path: Path) -> None:
    svc, sid = _service(tmp_path, generations=2)
    model = FaultyProvider([
        TransientProviderFailure("lost"), TransientProviderFailure("again"),
        TransientProviderFailure("still"),
    ])
    path = tmp_path / "limit.jsonl"
    recovery = SafeCheckpointRecoveryController(
        AcademicCheckpointAutopilot(svc, model),
        audit_path=path, pause=lambda _: None,
    )
    with pytest.raises(ResearchReviewRequired) as caught:
        recovery.run(sid, max_generations=2)
    assert caught.value.action == RecoveryAction.RETRY_EXHAUSTED
    assert model.calls == 3
    assert svc.get({"session_id": sid})["completed_generations"] == 0
    logs = [json.loads(line) for line in path.read_text().splitlines()]
    assert [record["decision"] for record in logs] == [
        "RETRY_TRANSIENT", "RETRY_TRANSIENT", "RETRY_EXHAUSTED",
    ]


def test_schema_failure_has_one_retry_then_holds(tmp_path: Path) -> None:
    svc, sid = _service(tmp_path, generations=2)

    class InvalidOnce(FaultyProvider):
        def propose(self, context: dict) -> dict:
            if self.calls == 0:
                self.calls += 1
                return {"bad": "schema"}
            return super().propose(context)

    model = InvalidOnce([])
    recovery = SafeCheckpointRecoveryController(
        AcademicCheckpointAutopilot(svc, model),
        audit_path=tmp_path / "schema.jsonl",
    )
    result = recovery.run(sid, max_generations=2)
    assert result["completed_generations"] == 2
    assert json.loads((tmp_path / "schema.jsonl").read_text().splitlines()[0])[
        "decision"
    ] == "REPAIR_MODEL_OUTPUT"


@pytest.mark.parametrize("error,expected", [
    (ProviderPolicyRefusal("blocked"), RecoveryAction.HOLD_POLICY),
    (PermissionError("forbidden"), RecoveryAction.HOLD_POLICY),
    (TransientProviderFailure("brief"), RecoveryAction.RETRY_TRANSIENT),
    (RuntimeError("unknown"), RecoveryAction.HOLD_UNKNOWN),
])
def test_failure_classifier_is_typed_not_textual(
    error: BaseException, expected: RecoveryAction,
) -> None:
    assert classify_research_failure(error) == expected
    assert classify_research_failure(RuntimeError("policy denied")) == (
        RecoveryAction.HOLD_UNKNOWN
    )


def test_failure_after_three_valid_generations_preserves_all_three(tmp_path: Path) -> None:
    svc, sid = _service(tmp_path, generations=4)

    class FailureAtFourthPlan(FaultyProvider):
        def __init__(self) -> None:
            super().__init__([])
            self.scripted = TenGenerationScriptedProvider()
            self.interrupted = False

        def propose(self, context: dict) -> dict:
            if (
                context.get("generation") == 4
                and context.get("output_contract") == "AlgorithmPlan"
                and not self.interrupted
            ):
                self.interrupted = True
                raise TransientProviderFailure("network lost after 3 commits")
            return self.scripted.propose(context)

    provider = FailureAtFourthPlan()
    recover = SafeCheckpointRecoveryController(
        AcademicCheckpointAutopilot(svc, provider),
        audit_path=tmp_path / "batch.jsonl",
    )
    report = recover.run(sid, max_generations=4)
    assert report["completed_generations"] == 4
    assert svc.get({"session_id": sid})["status"] == "COMPLETED"
    assert len({g["evidence_hash"] for g in svc.get({"session_id": sid})["history"]}) == 4
    assert all(
        svc.evaluate_experiments({"session_id": sid, "generation": gen})[
            "original_generation_evidence_hash"
        ] == svc.get({"session_id": sid})["history"][gen-1]["evidence_hash"]
        for gen in range(1, 5)
    )


def test_lost_server_reply_after_commit_rechecks_state_not_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc, sid = _service(tmp_path, generations=2)
    model = FaultyProvider([])
    original = svc.submit_diagnosis
    attempts = [0]

    def committed_then_lost_reply(args: dict) -> dict:
        result = original(args)
        attempts[0] += 1
        if attempts[0] == 1:
            raise TransientProviderFailure("accepted but reply lost")
        return result

    monkeypatch.setattr(svc, "submit_diagnosis", committed_then_lost_reply)
    recover = SafeCheckpointRecoveryController(
        AcademicCheckpointAutopilot(svc, model),
        audit_path=tmp_path / "reply.jsonl",
    )
    result = recover.run(sid, max_generations=2)
    assert result["completed_generations"] == 2
    assert attempts[0] == 2  # No replay of first committed diagnosis.
    assert len(svc.get({"session_id": sid})["history"]) == 2
    assert all(
        svc.evaluate_experiments({"session_id": sid, "generation": gen})[
            "original_generation_evidence_hash"
        ] == svc.get({"session_id": sid})["history"][gen-1]["evidence_hash"]
        for gen in (1, 2)
    )


def test_autopilot_exposes_explicit_resumable_foreground_entrypoint(tmp_path: Path) -> None:
    svc, sid = _service(tmp_path, generations=2)
    provider = FaultyProvider([TransientProviderFailure("brief")])
    result = AcademicCheckpointAutopilot(svc, provider).run_resumable(
        sid, max_generations=2,
        audit_path=tmp_path / "resumable" / "recovery.jsonl",
    )
    assert result["completed_generations"] == 2
    assert svc.get({"session_id": sid})["completed_generations"] == 2
    assert len((tmp_path / "resumable" / "recovery.jsonl").read_text().splitlines()) == 1
