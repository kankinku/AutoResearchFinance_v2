"""End-to-end checkpointed campaign, including failed precommits and replay safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.gpt_guided_research_service import GPTGuidedResearchService
from research.llm.guided_campaign_runner import (
    CampaignPlanError,
    GuidedCampaignRunner,
    JournalIntegrityError,
)
from tests.integrations.test_guided_adaptive_director import _decision

DATA = "data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet"
SOURCE = "strategies/normalized/0a805e67c88e16da-4.json"


class SimulatedGuided:
    """Fast mock for 40-generation orchestration; not a simulated alpha result."""

    def __init__(self, root):
        self.state_dir = root
        self.session_id = "a" * 32
        self.count = 0
        self.calls = 0
        self.requested = 40
        self.interrupted = False

    def get(self, sid):
        assert sid == self.session_id
        status = (
            "INTERRUPTED"
            if self.interrupted
            else "COMPLETED"
            if self.count >= self.requested
            else "AWAITING_GPT"
        )
        return {
            "session_id": sid,
            "status": status,
            "completed_generations": self.count,
            "requested_generations": self.requested,
            "orders_enabled": False,
            "sealed_oos_evaluated": False,
            "adaptive_research_controller": True,
            "require_execution_change": True,
            "generation": self.count + 1 if status == "AWAITING_GPT" else None,
            "checkpoint_token": f"checkpoint-{self.count}" if status == "AWAITING_GPT" else None,
            "last_run_id": f"run-{self.count}" if self.count else None,
            "research_director_brief": {"context_digest": f"digest-{self.count}"},
            "previous_failed_gates": ["validation"] if self.count else [],
            "controlled_training_memory": {
                "verified_generations": self.count,
                "two_parent_controls_verified": 0,
            },
        }

    def submit(self, args):
        self.calls += 1
        assert args["checkpoint_token"] == f"checkpoint-{self.count}"
        if args["intent"].get("rationale") == "known duplicate":
            raise ValueError("DUPLICATE_EXECUTION_TRACE: observed identical costed fills")
        self.count += 1
        return self.get(self.session_id)

    def reconcile(self, sid):
        return {**self.get(sid), "reconciliation": "UNVERIFIED_EVALUATION"}


def _mockplanner(checkpoint, failures):
    return {
        "source_path": SOURCE,
        "intent": {
            "mode": "mixed",
            "parent_ids": ["golden_cross"],
            "rationale": "controlled hypothesis, real model required in production",
            "operations": [
                {
                    "op": "SET_PARAMETER",
                    "path": "risk.position_size_pct",
                    "value": float(checkpoint["generation"]),
                }
            ],
        },
        "research_decision": {
            "context_digest": checkpoint["research_director_brief"]["context_digest"],
            "research_mode": "EXPLORE",
        },
    }


def test_40_generation_checkpoint_resume_target_and_chain(tmp_path):
    svc = SimulatedGuided(tmp_path)
    campaign = GuidedCampaignRunner(svc)
    result = campaign.drive(session_id=svc.session_id, planner=_mockplanner, max_new_generations=15)
    assert result.newly_completed_generations == 15
    assert result.completed_generations == 15 and result.stop_reason == "BUDGET_REACHED"
    assert len(campaign.audit(svc.session_id)) == 30
    next_driver = GuidedCampaignRunner(svc)
    result2 = next_driver.drive(
        session_id=svc.session_id, planner=_mockplanner, max_new_generations=25
    )
    assert result2.newly_completed_generations == 25
    assert result2.completed_generations == 40 and result2.stop_reason == "TARGET_COMPLETED"
    assert svc.calls == 40 and result2.journal_verified_records == 80
    again = next_driver.drive(
        session_id=svc.session_id, planner=_mockplanner, max_new_generations=12
    )
    assert again.newly_completed_generations == 0 and again.stop_reason == "TARGET_COMPLETED"
    assert len(next_driver.audit(svc.session_id)) == 80
    assert not result2.orders_enabled and not result2.sealed_oos_evaluated


def test_plan_rejection_replans_without_consuming_gen_or_budget(tmp_path):
    svc = SimulatedGuided(tmp_path)
    runner = GuidedCampaignRunner(svc)
    observed = []

    def planner(point, failures):
        observed.append(tuple(failures))
        x = _mockplanner(point, failures)
        if not failures and point["generation"] == 1:
            x["intent"]["rationale"] = "known duplicate"
        return x

    result = runner.drive(
        session_id=svc.session_id,
        planner=planner,
        max_new_generations=2,
        max_replans_per_generation=2,
    )
    assert result.completed_generations == 2 and result.newly_completed_generations == 2
    assert result.attempted_plans == 3 and result.rejected_plans == 1
    assert len(observed[1]) == 1 and observed[1][0]["code"] == "DUPLICATE_EXECUTION_TRACE"
    assert [r["event"] for r in runner.audit(svc.session_id)].count("PRECOMMIT_REJECTED") == 1


def test_bounded_rejection_halts_without_guessing_or_unbounded_loop(tmp_path):
    svc = SimulatedGuided(tmp_path)
    runner = GuidedCampaignRunner(svc)

    def always_bad(point, failures):
        x = _mockplanner(point, failures)
        x["intent"]["rationale"] = "known duplicate"
        return x

    result = runner.drive(
        session_id=svc.session_id,
        planner=always_bad,
        max_new_generations=10,
        max_replans_per_generation=2,
    )
    assert result.stop_reason == "MAX_PRECOMMIT_REPLANS_EXHAUSTED"
    assert result.completed_generations == 0 and result.attempted_plans == 3
    assert result.rejected_plans == 3 and svc.count == 0


def test_refuses_invalid_planner_stale_context_and_journal_tamper(tmp_path):
    svc = SimulatedGuided(tmp_path)
    runner = GuidedCampaignRunner(svc)
    with pytest.raises(ValueError, match="EXTERNAL_GPT_PLAN_PROVIDER_REQUIRED"):
        runner.drive(session_id=svc.session_id, planner=None, max_new_generations=1)
    with pytest.raises(CampaignPlanError, match="STALE_CONTEXT"):
        runner.drive(
            session_id=svc.session_id,
            planner=lambda point, rejects: {
                **_mockplanner(point, rejects),
                "research_decision": {"context_digest": "outdated"},
            },
            max_new_generations=1,
        )
    runner.drive(session_id=svc.session_id, planner=_mockplanner, max_new_generations=1)
    f = runner._journal_file(svc.session_id)
    raw = f.read_text()
    f.write_text(raw.replace("GENERATION_COMMITTED", "GENERATION_FABRICATED"))
    with pytest.raises(JournalIntegrityError, match="tampered"):
        runner.drive(session_id=svc.session_id, planner=_mockplanner, max_new_generations=1)
    assert svc.count == 1


def test_interrupted_evidence_never_replays_candidate(tmp_path):
    svc = SimulatedGuided(tmp_path)
    svc.interrupted = True
    result = GuidedCampaignRunner(svc).drive(
        session_id=svc.session_id, planner=_mockplanner, max_new_generations=7
    )
    assert result.stop_reason == "INTERRUPTED_RECONCILIATION_REQUIRED"
    assert svc.calls == 0


def test_real_guided_adaptive_resumes_three_generations_with_failed_parent_and_real_controls(
    tmp_path,
):
    root = Path(__file__).resolve().parents[2]
    service = GPTGuidedResearchService(project_root=root, state_dir=tmp_path / "real-campaign")
    point = service.start(
        {
            "data_path": DATA,
            "generations": 3,
            "seed": 167732,
            "count": 1,
            "method": "grid",
            "require_execution_change": True,
            "allow_research_parent_inheritance": True,
            "adaptive_research_controller": True,
            "benchmark_mode": "QQQ_COSTED_NEXT_OPEN_DEV_V1",
        }
    )
    runner = GuidedCampaignRunner(service)
    transcript = []

    def planner(checkpoint, rejections):
        gen = checkpoint["generation"]
        transcript.append(
            {
                "generation": gen,
                "failed_gates": list(checkpoint["previous_failed_gates"]),
                "feedback_digest": checkpoint["research_director_brief"]["context_digest"],
                "rejections": len(rejections),
            }
        )
        # External planner chooses different experiments based on actual failed
        # controls; this scripted unit test is NOT evidence of GPT autonomy.
        if gen == 1:
            parent = None
            mode = "EXPLORE"
            ops = [{"op": "SET_PARAMETER", "path": "risk.position_size_pct", "value": 90.0}]
        elif gen == 2:
            parent = 1
            mode = "DIAGNOSE_FAILURE"
            ops = [{"op": "SET_PARAMETER", "path": "risk.position_size_pct", "value": 75.0}]
        else:
            parent = 2
            mode = "TEST_SINGLE_FACTOR"
            assert checkpoint["controlled_training_memory"]["verified_generations"] == 2
            ops = [{"op": "SET_PARAMETER", "path": "indicators.sma_fast.period", "value": 10}]
        return {
            "source_path": SOURCE,
            "intent": {
                "mode": "mixed",
                "parent_ids": ["golden_cross"],
                "rationale": "External GPT audit plan: explicit costed single-factor variant",
                "operations": ops,
            },
            "research_parent_generation": parent,
            "research_decision": _decision(
                checkpoint["research_director_brief"], mode=mode, parent=parent
            ),
        }

    first = runner.drive(session_id=point["session_id"], planner=planner, max_new_generations=2)
    assert first.newly_completed_generations == 2 and first.stop_reason == "BUDGET_REACHED"
    assert first.journal_verified_records == 4
    second = GuidedCampaignRunner(service).drive(
        session_id=point["session_id"], planner=planner, max_new_generations=3
    )
    assert second.completed_generations == 3 and second.newly_completed_generations == 1
    assert second.stop_reason == "TARGET_COMPLETED"
    state = service.get(point["session_id"])
    assert state["learning_feedback"]["evaluated_candidates"] == 3
    assert state["learning_feedback"]["failed_candidates_included"] == 3
    assert state["controlled_training_memory"]["verified_generations"] == 3
    assert len({x["feedback_digest"] for x in transcript}) == 3
    assert all(not x["rejections"] for x in transcript)
    assert not state["orders_enabled"] and not state["sealed_oos_evaluated"]


def test_after_commit_client_crash_recovers_original_run_without_double_execution(tmp_path):
    class CommitThenCrash(SimulatedGuided):
        crashed = False

        def get(self, sid):
            out = super().get(sid)
            out["history"] = [
                {"generation": n, "run_id": f"run-{n}"} for n in range(1, self.count + 1)
            ]
            return out

        def submit(self, args):
            result = super().submit(args)
            if not self.crashed:
                self.crashed = True
                raise ConnectionError("client disconnected AFTER immutable evaluator committed")
            return result

    service = CommitThenCrash(tmp_path)
    runner = GuidedCampaignRunner(service)
    with pytest.raises(ConnectionError, match="AFTER immutable"):
        runner.drive(session_id=service.session_id, planner=_mockplanner, max_new_generations=3)
    assert service.count == 1 and service.calls == 1
    rows = runner.audit(service.session_id)
    assert len(rows) == 1 and rows[0]["event"] == "PLAN_RECEIVED"
    # A new process observes the committed step and records recovery, not replay.
    resumed = GuidedCampaignRunner(service).drive(
        session_id=service.session_id, planner=_mockplanner, max_new_generations=2
    )
    assert resumed.completed_generations == 3 and resumed.newly_completed_generations == 2
    assert service.calls == 3
    audit = GuidedCampaignRunner(service).audit(service.session_id)
    assert sum(x["event"] == "RECOVERED_COMMITTED_GENERATION" for x in audit) == 1
    assert any(x["details"].get("worker_replayed") is False for x in audit)


def test_resume_recovery_refuses_missing_signed_step(tmp_path):
    class MissingImmutableHistory(SimulatedGuided):
        def submit(self, args):
            super().submit(args)
            raise ConnectionError("lost request after commit")

    service = MissingImmutableHistory(tmp_path)
    runner = GuidedCampaignRunner(service)
    with pytest.raises(ConnectionError):
        runner.drive(session_id=service.session_id, planner=_mockplanner, max_new_generations=3)
    with pytest.raises(JournalIntegrityError, match="MISSING_SIGNED_STEP"):
        runner.drive(session_id=service.session_id, planner=_mockplanner, max_new_generations=3)
    assert service.calls == 1 and service.count == 1


def test_per_session_lock_prevents_concurrent_planners_and_duplicate_journal(tmp_path):
    import fcntl
    import os

    service = SimulatedGuided(tmp_path)
    runner = GuidedCampaignRunner(service)
    lock_path = str(runner._journal_file(service.session_id)) + ".lock"
    runner.root.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(RuntimeError, match="CAMPAIGN_ALREADY_RUNNING"):
            runner.drive(session_id=service.session_id, planner=_mockplanner, max_new_generations=2)
        assert service.calls == 0
    finally:
        os.close(fd)
    out = runner.drive(session_id=service.session_id, planner=_mockplanner, max_new_generations=2)
    assert out.completed_generations == 2
    assert out.journal_verified_records == 4
