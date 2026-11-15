"""Autopilot checks with scripted proposals: NOT evidence of actual LLM research."""
from pathlib import Path

import pytest

from application.academic_checkpoint_service import AcademicMCPCheckpointService
from core.data.parquet import ParquetDataProvider
from research.llm.checkpoint_autopilot import (
    AcademicCheckpointAutopilot,
    AutonomousLoopError,
)
from tests.research.test_academic_algorithm_plan import _market, _plan
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


class TenGenerationScriptedProvider:
    """Deterministic varied strategy drafts, diagnostic backed by actual trace IDs."""

    def __init__(self) -> None:
        self.calls = 0
        self.diagnoses = 0
        self.context_directions: list[dict] = []
        self.fail_diagnosis_once = False

    def propose(self, context):
        if context.get('output_contract') == 'AlgorithmPlan':
            generation = context['generation']
            self.calls += 1
            self.context_directions.append(context['research_direction'])
            names = [
                'time_series_momentum', 'previous_range_breakout',
                'sma_pullback_20', 'dual_sma_trend_50',
                'ema_direction_20', 'range_low_reclaim_20',
            ]
            n = generation - 1
            plan = _plan().model_dump(mode='json')
            plan['plan_id'] = f'nontrivial_generation_{generation:02d}'
            for branch, case in enumerate(plan['cases']):
                case['votes'] = [
                    {'indicator_id': names[(n + 2 * branch) % 6], 'weight': 0.7},
                    {'indicator_id': names[(n + 2 * branch + 1) % 6], 'weight': 0.3},
                ]
                case['min_score'] = (0.25, 0.55, 0.8)[n // 6 % 3]
                case['when']['threshold'] = (0.0001, 0.00001, 0.0003)[n // 18 % 3]
            return plan
        self.diagnoses += 1
        if self.fail_diagnosis_once:
            self.fail_diagnosis_once = False
            raise RuntimeError('injected remote provider outage before diagnosis')
        return ScriptedResearcher().propose(context)


def _service(tmp_path: Path, generations=10):
    root = tmp_path / 'project'
    (root / 'data').mkdir(parents=True)
    ParquetDataProvider.write(root / 'data' / 'study.parquet', _market())
    svc = AcademicMCPCheckpointService(project_root=root, state_dir=tmp_path / 'state')
    started = svc.start({'data_path': 'data/study.parquet', 'generations': generations})
    return svc, started['session_id']


def test_10_cycles_complete_under_single_foreground_run_and_use_s7_feedback(tmp_path: Path):
    svc, sid = _service(tmp_path)
    scripted = TenGenerationScriptedProvider()
    result = AcademicCheckpointAutopilot(svc, scripted).run(sid, max_generations=10)
    assert result['status'] == 'COMPLETED'
    assert result['completed_generations'] == 10
    assert result['advanced_generations_this_call'] == 10
    assert result['external_model_proposals_this_call'] == 20
    assert result['measured_hypotheses_read_or_executed'] == 10
    assert scripted.calls == 10 and scripted.diagnoses == 10
    assert scripted.context_directions[0]['recommended_mode'] == 'EXPLORE'
    assert scripted.context_directions[1]['experiment_outcome_count'] == 1
    assert result['final_report']['generations_completed'] == 10
    assert result['broker_executable'] is False
    state = svc.get({'session_id': sid})
    assert len(state['history']) == 10
    assert len({r['evidence_hash'] for r in state['history']}) == 10
    assert len({r['algorithm_semantic_hash'] for r in state['history']}) == 10
    assert state['orders_enabled'] is False
    for n in range(1, 11):
        proof = svc.evaluate_experiments({'session_id': sid, 'generation': n})
        assert proof['original_generation_evidence_hash'] == state['history'][n-1][
            'evidence_hash'
        ]
    replay = AcademicCheckpointAutopilot(svc, scripted).run(sid, max_generations=10)
    assert replay['advanced_generations_this_call'] == 0
    assert replay['external_model_proposals_this_call'] == 0
    assert svc.get({'session_id': sid})['history'] == state['history']


def test_model_diagnosis_failure_resumes_from_saved_plan_without_duplicate(tmp_path: Path):
    svc, sid = _service(tmp_path, generations=2)
    model = TenGenerationScriptedProvider()
    model.fail_diagnosis_once = True
    with pytest.raises(RuntimeError, match='outage'):
        AcademicCheckpointAutopilot(svc, model).run(sid, max_generations=2)
    waiting = svc.get({'session_id': sid})
    assert waiting['checkpoint_phase'] == 'AWAITING_DIAGNOSIS'
    assert waiting['completed_generations'] == 0
    assert model.calls == 1
    completed = AcademicCheckpointAutopilot(svc, model).run(sid, max_generations=2)
    assert completed['status'] == 'COMPLETED'
    assert model.calls == 2  # no extra plan for the interrupted generation
    assert model.diagnoses == 3
    assert svc.get({'session_id': sid})['completed_generations'] == 2


def test_run_bounded_can_stop_after_exact_generations_then_resume(tmp_path: Path):
    svc, sid = _service(tmp_path, generations=3)
    model = TenGenerationScriptedProvider()
    runner = AcademicCheckpointAutopilot(svc, model)
    first = runner.run(sid, max_generations=1)
    assert first['status'] == 'AWAITING_PROVIDER'
    assert first['completed_generations'] == 1
    evidence = svc.get({'session_id': sid})['history'][0]['evidence_hash']
    second = runner.run(sid, max_generations=2)
    assert second['status'] == 'COMPLETED'
    assert second['advanced_generations_this_call'] == 2
    assert svc.get({'session_id': sid})['history'][0]['evidence_hash'] == evidence


def test_refuse_invalid_budget_and_does_not_override_interrupted(tmp_path: Path):
    svc, sid = _service(tmp_path)
    model = TenGenerationScriptedProvider()
    runner = AcademicCheckpointAutopilot(svc, model)
    for invalid in (0, 101, True):
        with pytest.raises(AutonomousLoopError, match='max_generations'):
            runner.run(sid, max_generations=invalid)
    with svc._connect() as db:
        db.execute('UPDATE stages SET phase=? WHERE session_id=?', ('INTERRUPTED', sid))
    with pytest.raises(AutonomousLoopError, match='checkpoint'):
        runner.run(sid, max_generations=10)
    assert not model.calls


class _ProxyService:
    """Wrap real DEVELOPMENT fixture, injecting only one compromised return."""

    def __init__(self, delegate, *, corrupt_s7=None, privilege=None):
        self.delegate = delegate
        self.corrupt_s7 = corrupt_s7
        self.privilege = privilege

    def get(self, args):
        state = self.delegate.get(args)
        if self.privilege is not None:
            return {**state, **self.privilege}
        return state

    def submit_plan(self, args):
        return self.delegate.submit_plan(args)

    def submit_diagnosis(self, args):
        return self.delegate.submit_diagnosis(args)

    def evaluate_experiments(self, args):
        from copy import deepcopy

        proof = deepcopy(self.delegate.evaluate_experiments(args))
        if self.corrupt_s7 == "missing_trials":
            proof["report"]["experiments"] = []
        elif self.corrupt_s7 == "other_hypothesis":
            proof["report"]["experiments"][0]["hypothesis_id"] = "fake_alternative"
        elif self.corrupt_s7 == "wrong_session":
            proof["session_id"] = "f" * 32
        elif self.corrupt_s7 == "wrong_report_hash":
            proof["record_hash"] = "f" * 64
        return proof


@pytest.mark.parametrize(
    "corruption",
    ["missing_trials", "other_hypothesis", "wrong_session", "wrong_report_hash"],
)
def test_autopilot_blocks_forged_s7_before_reporting_completion(
    tmp_path: Path, corruption: str,
):
    svc, sid = _service(tmp_path, generations=1)
    provider = TenGenerationScriptedProvider()
    proxied = _ProxyService(svc, corrupt_s7=corruption)
    with pytest.raises(AutonomousLoopError, match="S7|paired|integrity"):
        AcademicCheckpointAutopilot(proxied, provider).run(sid, max_generations=1)
    state = svc.get({"session_id": sid})
    assert state["completed_generations"] == 1
    assert len(state["history"]) == 1
    assert provider.calls == 1 and provider.diagnoses == 1
    # The canonical saved report stays intact and a safe retry makes no
    # additional provider calls or duplicated generation.
    restored = AcademicCheckpointAutopilot(svc, provider).run(sid, max_generations=1)
    assert restored["completed_generations"] == 1
    assert restored["advanced_generations_this_call"] == 0
    assert provider.calls == 1 and provider.diagnoses == 1


@pytest.mark.parametrize(
    "privilege", [{"orders_enabled": True}, {"independent_oos_approved": True}],
)
def test_autopilot_rejects_promoted_privilege_before_model_or_cycle(
    tmp_path: Path, privilege: dict,
):
    svc, sid = _service(tmp_path, generations=1)
    provider = TenGenerationScriptedProvider()
    with pytest.raises(AutonomousLoopError, match="order|OOS|research.only"):
        AcademicCheckpointAutopilot(
            _ProxyService(svc, privilege=privilege), provider,
        ).run(sid, max_generations=1)
    assert provider.calls == 0 and provider.diagnoses == 0
    assert svc.get({"session_id": sid})["completed_generations"] == 0


def test_autopilot_does_not_attest_real_model_from_scripted_provider(tmp_path: Path):
    svc, sid = _service(tmp_path, generations=1)
    result = AcademicCheckpointAutopilot(
        svc, TenGenerationScriptedProvider(),
    ).run(sid, max_generations=1)
    assert result["actual_model_invocation_attested"] is False
    assert result["model_transport_tested"] == "CALLER_SUPPLIED_PROVIDER_ONLY"
    assert result["broker_executable"] is False


def test_missing_s7_after_completed_checkpoint_is_repaired_before_new_plan(
    tmp_path: Path,
):
    svc, sid = _service(tmp_path, generations=2)
    model = TenGenerationScriptedProvider()
    runner = AcademicCheckpointAutopilot(svc, model)
    first = runner.run(sid, max_generations=1)
    assert first["completed_generations"] == 1
    original = svc.get({"session_id": sid})["history"][0]["evidence_hash"]
    with svc._connect() as db:
        db.execute(
            "DELETE FROM experiment_reports WHERE session_id=? AND generation=1",
            (sid,),
        )
    assert svc.get({"session_id": sid})["completed_generations"] == 1
    completed = runner.run(sid, max_generations=1)
    assert completed["completed_generations"] == 2
    assert completed["advanced_generations_this_call"] == 1
    assert model.calls == 2 and model.diagnoses == 2
    history = svc.get({"session_id": sid})["history"]
    assert len(history) == 2 and history[0]["evidence_hash"] == original
    proof = svc.evaluate_experiments({"session_id": sid, "generation": 1})
    assert proof["original_generation_evidence_hash"] == original
    replay = runner.run(sid, max_generations=1)
    assert replay["advanced_generations_this_call"] == 0
    assert model.calls == 2


def test_running_state_requires_operator_reconciliation_no_spontaneous_replay(
    tmp_path: Path,
):
    svc, sid = _service(tmp_path, generations=1)
    state = svc.get({"session_id": sid})
    with svc._connect() as db:
        db.execute(
            "UPDATE stages SET phase='RUNNING' WHERE session_id=?", (sid,),
        )
    provider = TenGenerationScriptedProvider()
    with pytest.raises(AutonomousLoopError, match="reconcile"):
        AcademicCheckpointAutopilot(svc, provider).run(sid, max_generations=1)
    assert provider.calls == 0 and provider.diagnoses == 0
    after = svc.reconcile({"session_id": sid})
    assert after["completed_generations"] == 0
    assert after["checkpoint_token"] != state["checkpoint_token"]
    assert len(after["history"]) == 0
    resumed = AcademicCheckpointAutopilot(svc, provider).run(
        sid, max_generations=1,
    )
    assert resumed["completed_generations"] == 1
    assert resumed["actual_model_invocation_attested"] is False
