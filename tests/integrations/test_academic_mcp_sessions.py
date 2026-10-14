"""Stable URL MCP: externally GPT-authored algorithm-plan/diagnosis checkpoints."""
from pathlib import Path

import pytest

from core.data.parquet import ParquetDataProvider
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from integrations.codex_mcp_core import create_mcp_server
from tests.research.test_academic_algorithm_plan import _market, _plan
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def _setup(tmp_path: Path):
    root = tmp_path / 'project'
    root.mkdir()
    (root/'data').mkdir()
    ParquetDataProvider.write(root/'data'/'study.parquet', _market())
    server = create_mcp_server(project_root=root, state_dir=tmp_path/'state')
    started = server._dispatch('start_algorithm_research', {
        'data_path':'data/study.parquet','generations':2,
    })
    return server, started


def test_additive_mcp_tools_preserve_old_tool_names_and_paths():
    schema = {x['name']: x for x in chatgpt_tools()}
    for name in ('start_algorithm_research', 'get_algorithm_research',
                 'submit_algorithm_plan','submit_algorithm_diagnosis',
                 'resume_algorithm_research'):
        assert name in schema
        assert schema[name]['inputSchema']['additionalProperties'] is False
        assert 'url' not in schema[name]['inputSchema']['properties']
    assert 'run_research_step' in schema
    assert 'start_guided_research' in schema
    assert 'start_research_batch' in schema
    assert not any('order' in name or 'secret' in name for name in schema)


def test_external_gpt_can_author_two_real_data_generations_without_reinstall(tmp_path: Path):
    server, started = _setup(tmp_path)
    sid, token = started['session_id'], started['checkpoint_token']
    scripted = ScriptedResearcher()
    for n in (1,2):
        plan = scripted.propose(started['model_context'])
        presented = server._dispatch('submit_algorithm_plan', {
            'session_id':sid,'checkpoint_token':token,'plan':plan,
        })
        assert presented['status'] == 'AWAITING_DIAGNOSIS'
        diagnosis = scripted.propose(presented['model_context'])
        result = server._dispatch('submit_algorithm_diagnosis', {
            'session_id':sid,'checkpoint_token':presented['checkpoint_token'],
            'diagnosis':diagnosis,
        })
        assert result['completed_generations'] == n
        assert result['history'][n-1]['audit_hash']
        assert result['history'][n-1]['hypothesis_ids']
        if n == 1:
            assert result['status'] == 'AWAITING_PROVIDER'
            token = result['checkpoint_token']
            started = result
    assert result['status'] == 'COMPLETED'
    assert result['orders_enabled'] is False
    assert result['real_model_connection_verified'] is False
    fetched=server._dispatch('get_algorithm_research', {'session_id':sid})
    assert fetched['completed_generations']==2
    assert fetched['history']==result['history']
    assert not any('api_key' in str(r).lower() for r in result['history'])


def test_plan_and_diagnosis_tokens_protect_checkpoint(tmp_path: Path):
    server, started=_setup(tmp_path)
    with pytest.raises(ValueError, match='token'):
        server._dispatch('submit_algorithm_plan', {
            'session_id':started['session_id'], 'checkpoint_token':'0'*32,
            'plan':_plan().model_dump(mode='json'),
        })
    assert server._dispatch('get_algorithm_research', {
        'session_id':started['session_id']})['completed_generations']==0
    staged=server._dispatch('submit_algorithm_plan', {
        'session_id':started['session_id'],
        'checkpoint_token':started['checkpoint_token'],
        'plan':_plan().model_dump(mode='json'),
    })
    assert staged['status']=='AWAITING_DIAGNOSIS'
    with pytest.raises(ValueError, match='token'):
        server._dispatch('submit_algorithm_diagnosis', {
            'session_id':started['session_id'],'checkpoint_token':'f'*32,
            'diagnosis':{},
        })
    assert server._dispatch('get_algorithm_research', {
        'session_id':started['session_id']})['status']=='AWAITING_DIAGNOSIS'
    with pytest.raises(ValueError, match='state|plan'):
        server._dispatch('submit_algorithm_plan', {
            'session_id':started['session_id'],
            'checkpoint_token':started['checkpoint_token'],
            'plan':_plan().model_dump(mode='json'),
        })


def test_reject_unauthorized_path_and_oos_before_prompt(tmp_path: Path):
    root=tmp_path/'root'
    root.mkdir()
    server=create_mcp_server(project_root=root,state_dir=tmp_path/'state')
    with pytest.raises((ValueError, PermissionError, FileNotFoundError)):
        server._dispatch('start_algorithm_research', {
            'data_path':'../secret.parquet','generations':2,
        })
    for illegal in ({'data_path':'data/no.parquet','generations':2,'public_url':'fake'},
                    {'data_path':'data/no.parquet','generations':True}):
        with pytest.raises(ValueError):
            server._dispatch('start_algorithm_research', illegal)


def test_cancel_staged_diagnosis_preserves_audit_generation_count(tmp_path: Path):
    server, started = _setup(tmp_path)
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': started['session_id'],
        'checkpoint_token': started['checkpoint_token'],
        'plan': _plan().model_dump(mode='json'),
    })
    cancelled = server._dispatch('cancel_algorithm_research', {
        'session_id': started['session_id'],
        'checkpoint_token': staged['checkpoint_token'],
    })
    assert cancelled['status'] == 'CANCELLED'
    assert cancelled['completed_generations'] == 0
    assert cancelled['final_report']['completion_reason'] == 'CANCELLED_AT_CHECKPOINT'
    assert 'model_context' not in cancelled
    with pytest.raises(ValueError, match='state|token|checkpoint'):
        server._dispatch('submit_algorithm_diagnosis', {
            'session_id': started['session_id'],
            'checkpoint_token': staged['checkpoint_token'],
            'diagnosis': {},
        })
    assert server._dispatch('get_algorithm_research', {
        'session_id': started['session_id'],
    })['status'] == 'CANCELLED'


def test_cancel_requires_current_checkpoint_token(tmp_path: Path):
    server, started = _setup(tmp_path)
    with pytest.raises(ValueError, match='token'):
        server._dispatch('cancel_algorithm_research', {
            'session_id': started['session_id'],
            'checkpoint_token': '0' * 32,
        })
    assert server._dispatch('get_algorithm_research', {
        'session_id': started['session_id'],
    })['status'] == 'AWAITING_PROVIDER'


def test_explicit_reconcile_after_crash_preserves_completed_generation(tmp_path: Path):
    server, started = _setup(tmp_path)
    sid = started['session_id']
    scripted = ScriptedResearcher()
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': sid, 'checkpoint_token': started['checkpoint_token'],
        'plan': scripted.propose(started['model_context']),
    })
    # Crash between stage claim and submitting diagnosis: no valid generation
    # has been committed; recovery must never silently invent one.
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    svc = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    with svc._connect() as db:
        db.execute("UPDATE stages SET phase='RUNNING' WHERE session_id=?", (sid,))
    recovery = server._dispatch('reconcile_algorithm_research', {'session_id': sid})
    assert recovery['status'] == 'AWAITING_PROVIDER'
    assert recovery['completed_generations'] == 0
    assert recovery['checkpoint_phase'] == 'AWAITING_PLAN'
    assert recovery['checkpoint_token'] != staged['checkpoint_token']
    with pytest.raises(ValueError, match='interrupted'):
        server._dispatch('resume_algorithm_research', {'session_id': sid})


def test_reconcile_finished_cycle_after_gateway_crash_does_not_repeat_work(tmp_path: Path):
    server, started = _setup(tmp_path)
    scripted = ScriptedResearcher()
    sid = started['session_id']
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': sid, 'checkpoint_token': started['checkpoint_token'],
        'plan': scripted.propose(started['model_context']),
    })
    from application.academic_checkpoint_service import (
        AcademicMCPCheckpointService,
        _SubmittedProvider,
    )
    svc = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    with svc._connect() as db:
        db.execute("UPDATE stages SET phase='RUNNING' WHERE session_id=?", (sid,))
    diagnosis = scripted.propose(staged['model_context'])
    with svc._connect() as db:
        row = db.execute('SELECT * FROM stages WHERE session_id=?', (sid,)).fetchone()
        assert row is not None
        import json
        plan = json.loads(row['plan_json'])
        catalog, market = svc._catalog(), svc._data(row['data_path'])
    svc.cycle.advance(sid, catalog, market, _SubmittedProvider(plan, diagnosis))
    recovered = server._dispatch('reconcile_algorithm_research', {'session_id': sid})
    assert recovered['status'] == 'AWAITING_PROVIDER'
    assert recovered['checkpoint_phase'] == 'AWAITING_PLAN'
    assert recovered['completed_generations'] == 1
    assert len(recovered['history']) == 1
    assert recovered['checkpoint_token'] != staged['checkpoint_token']

def test_resume_gateway_interrupted_before_cycle_claim(tmp_path: Path):
    server, started = _setup(tmp_path)
    sid = started['session_id']
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    svc = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    with svc._connect() as db:
        db.execute("UPDATE stages SET phase='INTERRUPTED' WHERE session_id=?", (sid,))
    result = server._dispatch('resume_algorithm_research', {'session_id': sid})
    assert result['status'] == 'AWAITING_PROVIDER'
    assert result['checkpoint_phase'] == 'AWAITING_PLAN'
    assert result['completed_generations'] == 0
    assert result['checkpoint_token'] != started['checkpoint_token']


def test_s7_controls_persist_and_inform_next_generation_without_replaying(tmp_path: Path):
    server, initial = _setup(tmp_path)
    model = ScriptedResearcher()
    sid = initial['session_id']
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': sid, 'checkpoint_token': initial['checkpoint_token'],
        'plan': model.propose(initial['model_context']),
    })
    finished = server._dispatch('submit_algorithm_diagnosis', {
        'session_id': sid, 'checkpoint_token': staged['checkpoint_token'],
        'diagnosis': model.propose(staged['model_context']),
    })
    assert finished['completed_generations'] == 1
    report = server._dispatch('evaluate_algorithm_experiments', {
        'session_id': sid, 'generation': 1,
    })
    assert report['report']['status'] == 'CONTROLLED_DEVELOPMENT_COMPARISON'
    assert report['report']['experiments'][0]['causal_status'] == 'NOT_ESTABLISHED'
    assert report['original_generation_evidence_hash'] == finished['history'][0]['evidence_hash']
    assert report['report']['audit_hash'] == finished['history'][0]['audit_hash']
    assert (
        report['report']['diagnostic_proposal_hash']
        == finished['history'][0]['diagnostic_proposal_hash']
    )
    assert report['record_hash']
    assert server._dispatch('evaluate_algorithm_experiments', {
        'session_id': sid, 'generation': 1,
    }) == report
    next_step = server._dispatch('get_algorithm_research', {'session_id': sid})
    assert next_step['completed_generations'] == 1
    assert (
        next_step['model_context']['prior_research']['controlled_experiments']['record_hash']
        == report['record_hash']
    )
    assert next_step['final_report'] is None


def test_s7_reject_invalid_generations_before_write(tmp_path: Path):
    server, started = _setup(tmp_path)
    for gen in (0, 1, 2, True):
        with pytest.raises(ValueError):
            server._dispatch('evaluate_algorithm_experiments', {
                'session_id': started['session_id'], 'generation': gen,
            })
    with pytest.raises(ValueError):
        server._dispatch('evaluate_algorithm_experiments', {
            'session_id': started['session_id'], 'generation': 1, 'sealed': True,
        })


def test_s7_v2_stored_diff_is_hash_checked(tmp_path: Path):
    server, initial = _setup(tmp_path)
    scripted = ScriptedResearcher()
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': initial['session_id'],
        'checkpoint_token': initial['checkpoint_token'],
        'plan': scripted.propose(initial['model_context']),
    })
    server._dispatch('submit_algorithm_diagnosis', {
        'session_id': initial['session_id'],
        'checkpoint_token': staged['checkpoint_token'],
        'diagnosis': scripted.propose(staged['model_context']),
    })
    report = server._dispatch('evaluate_algorithm_experiments', {
        'session_id': initial['session_id'], 'generation': 1,
    })
    outcome = report['report']['experiments'][0]
    assert 'execution_delta' in outcome
    assert len(outcome['development_windows']) == 4
    assert report['report']['evidence_hash']
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    svc = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    with svc._connect() as db:
        db.execute('UPDATE experiment_reports SET report_hash=?', ('0' * 64,))
    with pytest.raises(ValueError, match='integrity'):
        server._dispatch('evaluate_algorithm_experiments', {
            'session_id': initial['session_id'], 'generation': 1,
        })
