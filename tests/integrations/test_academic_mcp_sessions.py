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
        catalog, market = svc._catalog(row['catalog_version']), svc._data(row['data_path'])
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


def test_s6_new_starts_use_pinned_catalog_and_old_sessions_remain_readable(tmp_path: Path):
    server, original = _setup(tmp_path)
    previous = server._dispatch('get_algorithm_research', {'session_id': original['session_id']})
    assert previous['model_context']['catalog_version'] == 's6-v2'
    assert {'ema_direction_20', 'range_low_reclaim_20'} <= {
        x['indicator_id'] for x in previous['model_context']['verified_indicators']
    }
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    svc = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    # Simulate an older session created before the S6 deployment via
    # its previously pinned catalog, without altering any newer session.
    old_market = _market()
    from core.data.parquet import ParquetDataProvider
    ParquetDataProvider.write(tmp_path / 'project' / 'data' / 'legacy.parquet', old_market)
    old_catalog = svc._catalog('s3-v1')
    started = svc.cycle.start(old_catalog, old_market, generations=2)
    import uuid
    with svc._connect() as db:
        db.execute(
            'INSERT INTO stages(session_id,data_path,phase,token,catalog_version) '
            "VALUES(?,?,'AWAITING_PLAN',?,'s3-v1')",
            (started['session_id'], 'data/legacy.parquet', uuid.uuid4().hex),
        )
    legacy = server._dispatch('get_algorithm_research', {'session_id': started['session_id']})
    assert legacy['model_context']['catalog_version'] == 's3-v1'
    assert 'ema_direction_20' not in {
        x['indicator_id'] for x in legacy['model_context']['verified_indicators']
    }
    assert server._dispatch('get_algorithm_research', {
        'session_id': original['session_id'],
    })['model_context']['catalog_version'] == 's6-v2'


def test_s6_catalog_version_tampering_rejected_before_model_call(tmp_path: Path):
    server, session = _setup(tmp_path)
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    service = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    assert session['model_context']['catalog_version'] == 's6-v2'
    with service._connect() as db:
        db.execute('UPDATE stages SET catalog_version=? WHERE session_id=?',
                   ('s3-v1', session['session_id']))
    with pytest.raises(ValueError, match='catalog identity'):
        server._dispatch('get_algorithm_research', {'session_id':session['session_id']})
    with service._connect() as db:
        db.execute('UPDATE stages SET catalog_version=? WHERE session_id=?',
                   ('not-a-version', session['session_id']))
    with pytest.raises(ValueError, match='unknown pinned'):
        server._dispatch('get_algorithm_research', {'session_id':session['session_id']})


def test_s6_v2_external_provenance_pinned_and_v1_can_replay(tmp_path: Path):
    server, current = _setup(tmp_path)
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    from research.indicator_engine.external_reference import get_s6_external_reference
    from research.indicator_engine.s6_seed import S6_SIGNALS
    service = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    assert current['catalog_version'] == 's6-v2'
    assert len(current['model_context']['verified_indicators']) == 8
    newest = service._catalog('s6-v2')
    for signal in S6_SIGNALS:
        report = get_s6_external_reference(newest, signal.signal_id)
        assert report is not None and report.passed
        assert report.backend == 'pandas' and report.version
    old_catalog = service._catalog('s6-v1')
    market = _market()
    old = service.cycle.start(old_catalog, market, generations=2)
    from uuid import uuid4
    with service._connect() as db:
        db.execute(
            'INSERT INTO stages(session_id,data_path,phase,token,catalog_version) '
            'VALUES(?,?,?,?,?)',
            (old['session_id'], 'data/study.parquet', 'AWAITING_PLAN',
             uuid4().hex, 's6-v1'),
        )
    recovered = server._dispatch('get_algorithm_research', {
        'session_id': old['session_id'],
    })
    assert recovered['catalog_version'] == 's6-v1'
    assert recovered['completed_generations'] == 0
    assert service._catalog('s6-v1').database != newest.database


def test_s6_v2_provenance_tampering_fails_closed(tmp_path: Path):
    server, started = _setup(tmp_path)
    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    svc = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    verified = svc._catalog('s6-v2')
    with verified._connect() as db:
        db.execute(
            'UPDATE s6_external_provenance SET report_hash=? WHERE signal_id=?',
            ('0' * 64, 'ema_direction_20'),
        )
    with pytest.raises(ValueError, match='integrity'):
        server._dispatch('get_algorithm_research', {
            'session_id': started['session_id'],
        })


def test_s6_v2_backend_upgrade_blocks_new_sessions_but_reads_existing(tmp_path: Path, monkeypatch):
    server, created = _setup(tmp_path)
    from research.indicator_engine import external_reference
    monkeypatch.setattr(external_reference, '_backend_version', lambda: '3.999.99')
    still_readable = server._dispatch('get_algorithm_research', {
        'session_id': created['session_id'],
    })
    assert still_readable['catalog_version'] == 's6-v2'
    assert still_readable['session_id'] == created['session_id']
    with pytest.raises(ValueError, match='backend version changed'):
        server._dispatch('start_algorithm_research', {
            'data_path': 'data/study.parquet', 'generations': 1,
        })


def test_s8_research_direction_consumes_measured_experiments_without_claiming_alpha(tmp_path: Path):
    server, started = _setup(tmp_path)
    from tests.research.test_autonomous_academic_cycle import ScriptedResearcher
    provider = ScriptedResearcher()
    assert started['model_context']['research_direction']['recommended_mode'] == 'EXPLORE'
    sid = started['session_id']
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': sid, 'checkpoint_token': started['checkpoint_token'],
        'plan': provider.propose(started['model_context']),
    })
    finished = server._dispatch('submit_algorithm_diagnosis', {
        'session_id': sid, 'checkpoint_token': staged['checkpoint_token'],
        'diagnosis': provider.propose(staged['model_context']),
    })
    before = finished['model_context']['research_direction']
    assert before['completed_generations'] == 1
    assert before['recommended_mode'] == 'TEST_HYPOTHESIS'
    assert before['experiment_outcome_count'] == 0
    tested = server._dispatch('evaluate_algorithm_experiments', {
        'session_id': sid, 'generation': 1,
    })
    after = server._dispatch('get_algorithm_research', {'session_id': sid})
    budget = after['model_context']['research_direction']
    assert budget['completed_generations'] == 1
    assert budget['experiment_outcome_count'] == len(tested['report']['experiments'])
    assert budget['causal_status'] == 'NOT_ESTABLISHED'
    assert budget['llm_may_override'] is True
    assert budget['independent_oos_approved'] is False
    assert after['history'] == finished['history']
    assert server._dispatch('get_algorithm_research', {'session_id': sid})[
        'model_context']['research_direction'] == budget


def test_s8_legacy_experiment_without_execution_diff_remains_readable(tmp_path: Path):
    server, started = _setup(tmp_path)
    provider = ScriptedResearcher()
    sid = started['session_id']
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': sid, 'checkpoint_token': started['checkpoint_token'],
        'plan': provider.propose(started['model_context']),
    })
    completed = server._dispatch('submit_algorithm_diagnosis', {
        'session_id': sid, 'checkpoint_token': staged['checkpoint_token'],
        'diagnosis': provider.propose(staged['model_context']),
    })
    import json

    from application.academic_checkpoint_service import AcademicMCPCheckpointService
    from core.integrity.hashes import content_hash
    service = AcademicMCPCheckpointService(
        project_root=tmp_path / 'project', state_dir=tmp_path / 'state',
    )
    legacy = {
        'session_id': sid, 'generation': 1,
        'original_generation_evidence_hash': completed['history'][0]['evidence_hash'],
        'report': {
            'status': 'CONTROLLED_DEVELOPMENT_COMPARISON',
            'causal_status': 'NOT_ESTABLISHED',
            'experiments': [{
                'hypothesis_id': 'legacy',
                'status': 'NO_OBSERVED_EFFECT',
                'causal_status': 'NOT_ESTABLISHED',
            }],
        },
    }
    with service._connect() as db:
        db.execute(
            'INSERT INTO experiment_reports(session_id,generation,report_json,report_hash) '
            'VALUES(?,?,?,?)', (sid, 1, json.dumps(legacy), content_hash(legacy)),
        )
    state = server._dispatch('get_algorithm_research', {'session_id': sid})
    assert state['model_context']['research_direction']['experiment_outcome_count'] == 0
    assert (
        state['model_context']['prior_research']['controlled_experiments']['report']
        == legacy['report']
    )
    assert state['model_context']['research_direction']['causal_status'] == 'NOT_ESTABLISHED'
