"""P3 injected model tests. Mocked provider is NOT a real LLM call."""

from __future__ import annotations

import json

import pytest

from core.integrity.hashes import content_hash
from research.llm.inherited_checkpoint_autopilot import (
    ModelProposalAudit,
    P3InheritedCheckpointAutopilot,
    P3ResearchError,
)

PLAN = {
    "mode": "structure",
    "parent_ids": ["verified-parent"],
    "operations": [
        {
            "op": "REPLACE_RULE",
            "path": "exit.conditions.0",
            "condition": {"op": "less_equal", "left": "plan_vote_score", "value": 0.25},
        }
    ],
    "rationale": "Test controlled exit timing against an audited parent.",
}


class FakeProvider:
    def __init__(self):
        self.contexts = []

    def propose(self, context):
        self.contexts.append(context)
        if context.get("output_contract") == "InheritedResearchIntent":
            if context.get("precommit_rejection_feedback", {}).get("rejection_count"):
                return {
                    **PLAN,
                    "operations": [{"op": "CHANGE_AND_OR", "path": "entry.logic", "logic": "OR"}],
                }
            return dict(PLAN)
        return {
            "context_hash": "a" * 64,
            "audit_hash": "b" * 64,
            "strategy_hash": "c" * 64,
            "dataset_hash": "d" * 64,
            "summary": "Mocked diagnostic supported by a trade observation.",
            "hypotheses": [
                {
                    "hypothesis_id": "hyp_mock_01",
                    "observed_ids": ["trade_01"],
                    "mechanism": "Measured losing trades may be prolonged by exit timing.",
                    "alternative": "An earlier exit may also sacrifice profitable trades.",
                    "expected_metric": "max_drawdown",
                    "predicted_direction": "DECREASE",
                    "test_design": "RULE_STRUCTURE",
                    "control": "PARENT_UNCHANGED",
                    "next_intent": PLAN,
                }
            ],
        }


class FakeService:
    def __init__(self, reject_once=True):
        self.phase = "AWAITING_PLAN"
        self.reject_once = reject_once
        self.rejections = 0
        self.count = 452
        self.history = [{"evidence_hash": "previous-proof"}]
        self.token = "plan-token"

    def get(self, args):
        context = (
            {
                "output_contract": "InheritedResearchIntent",
                "counted_parent_inheritance_ready": True,
                "inherited_parent_strategy_id": "verified-parent",
                "precommit_rejection_feedback": {"rejection_count": self.rejections},
            }
            if self.phase == "AWAITING_PLAN"
            else {"schema": "research-diagnostic-context-v1"}
        )
        return {
            "checkpoint_phase": self.phase,
            "completed_generations": self.count,
            "history": list(self.history),
            "checkpoint_token": self.token,
            "model_context": context,
            "orders_enabled": False,
            "independent_oos_approved": False,
        }

    def submit_plan(self, args):
        assert args["checkpoint_token"] == self.token
        self.rejections += 1
        if self.reject_once and self.rejections == 1:
            raise ValueError("P2_PRECOMMIT_RISK_REJECTED: synthetic rejection")
        self.phase = "AWAITING_DIAGNOSIS"
        self.token = "diagnosis-token"
        return self.get(args)

    def submit_diagnosis(self, args):
        assert args["checkpoint_token"] == "diagnosis-token"
        self.phase = "COMPLETED"
        self.count = 453
        self.history.append(
            {
                "previous_evidence_hash": "previous-proof",
                "evidence_hash": "new-proof",
            }
        )
        return self.get(args)

    def evaluate_experiments(self, args):
        return {
            "original_generation_evidence_hash": "new-proof",
            "record_hash": "signed-s7-record",
            "report": {
                "experiments": [
                    {
                        "hypothesis_id": "mock_1",
                        "status": "NO_OBSERVED_EFFECT",
                        "same_fill_trace": True,
                        "delta": 0.0,
                    }
                ]
            },
        }


def test_p3_model_failure_feedback_retry_and_receipt_chain(tmp_path):
    service = FakeService()
    provider = FakeProvider()
    path = tmp_path / "receipts.jsonl"
    result = P3InheritedCheckpointAutopilot(
        service,
        provider,
        receipts=ModelProposalAudit(path, session_id="mock"),
        max_plan_attempts=3,
    ).run("mock", max_generations=1)
    assert result["new_generations"] == 1
    assert result["planning_proposals"] == 2
    assert result["diagnostic_proposals"] == 1
    assert result["typed_proposals_rejected"] == 1
    assert result["actual_model_invocation_attested"] is False
    assert provider.contexts[1]["precommit_rejection_feedback"]["rejection_count"] == 1
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == 4
    assert [r["result"] for r in records] == [
        "REJECTED_BY_S2_OR_P2",
        "S2_PLAN_STAGED",
        "COUNTED_GENERATION_COMMITTED",
        "S7_NO_OBSERVED_EFFECT",
    ]
    assert result["s7_no_effect_hypotheses"] == 1
    assert result["s7_measured_effect_hypotheses"] == 0
    assert result["last_s7_feedback"]["report_hash"] == "signed-s7-record"
    previous = None
    for record in records:
        assert record["previous_receipt_hash"] == previous
        assert record["receipt_hash"] == content_hash(
            {k: v for k, v in record.items() if k != "receipt_hash"}
        )
        previous = record["receipt_hash"]


def test_p3_strict_attempt_limit_keeps_checkpoint_intact(tmp_path):
    service = FakeService()
    with pytest.raises(P3ResearchError, match="MAX_MODEL_PROPOSAL_BUDGET_EXHAUSTED"):
        P3InheritedCheckpointAutopilot(
            service,
            FakeProvider(),
            receipts=ModelProposalAudit(tmp_path / "receipts.jsonl", session_id="mock"),
            max_plan_attempts=1,
        ).run("mock", max_generations=1)
    assert service.count == 452
    assert service.phase == "AWAITING_PLAN"


def test_p3_rejects_unsafe_phase_and_existing_log(tmp_path):
    service = FakeService()
    service.phase = "RUNNING"
    provider = FakeProvider()
    path = tmp_path / "proof.jsonl"
    with pytest.raises(P3ResearchError, match="safe waiting phase"):
        P3InheritedCheckpointAutopilot(
            service, provider, receipts=ModelProposalAudit(path, session_id="mock")
        ).run("mock", max_generations=1)
    assert not provider.contexts
    path.write_text("used\n")
    with pytest.raises(P3ResearchError, match="audit path exists"):
        ModelProposalAudit(path, session_id="mock")


def test_p3_explicit_receipt_resume_is_verified_and_session_bound(tmp_path):
    path = tmp_path / "receipts.jsonl"
    original = ModelProposalAudit(path, session_id="one")
    original.append(
        phase="PLAN",
        generation=453,
        context={"output_contract": "InheritedResearchIntent"},
        proposal=PLAN,
        result="REJECTED_BY_S2_OR_P2",
        evidence_hash="previous-proof",
    )
    resumed = ModelProposalAudit(path, session_id="one", resume=True)
    assert resumed.previous_hash == original.previous_hash
    with pytest.raises(P3ResearchError, match="session mismatch"):
        ModelProposalAudit(path, session_id="two", resume=True)
    text = path.read_text().replace("REJECTED_BY_S2_OR_P2", "APPROVED_BY_FORCE")
    path.write_text(text)
    with pytest.raises(P3ResearchError, match="chain or session mismatch"):
        ModelProposalAudit(path, session_id="one", resume=True)


class FakeTwoGenerationService(FakeService):
    def submit_diagnosis(self, args):
        assert self.phase == "AWAITING_DIAGNOSIS"
        previous = self.history[-1]["evidence_hash"]
        self.count += 1
        self.history.append(
            {
                "previous_evidence_hash": previous,
                "evidence_hash": f"generation-{self.count}-evidence",
            }
        )
        self.phase = "AWAITING_PLAN" if self.count == 453 else "COMPLETED"
        self.token = "plan-token"
        return self.get(args)

    def evaluate_experiments(self, args):
        generation = args["generation"]
        no_effect = generation == 453
        return {
            "original_generation_evidence_hash": self.history[-1]["evidence_hash"],
            "record_hash": f"generation-{generation}-s7-hash",
            "report": {
                "experiments": [
                    {
                        "hypothesis_id": f"hyp_{generation}",
                        "status": "NO_OBSERVED_EFFECT" if no_effect else "MEASURED_CHANGE",
                        "same_fill_trace": no_effect,
                        "delta": 0 if no_effect else 0.05,
                    }
                ]
            },
        }


def test_p3_no_effect_s7_report_changes_next_model_context(tmp_path):
    service = FakeTwoGenerationService(reject_once=False)
    provider = FakeProvider()
    report = P3InheritedCheckpointAutopilot(
        service,
        provider,
        receipts=ModelProposalAudit(tmp_path / "p3-feedback.jsonl", session_id="mock"),
        max_plan_attempts=2,
    ).run("mock", max_generations=2)
    assert report["new_generations"] == 2
    assert report["s7_no_effect_hypotheses"] == 1
    assert report["s7_measured_effect_hypotheses"] == 1
    followup_context = next(
        context
        for context in provider.contexts
        if context.get("last_s7_measured_feedback") is not None
    )
    feedback = followup_context["last_s7_measured_feedback"]
    assert feedback["generation"] == 453
    assert feedback["no_effect_count"] == 1
    assert feedback["hypotheses"][0]["status"] == "NO_OBSERVED_EFFECT"
    assert feedback["not_sealed_oos"] is True
