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
