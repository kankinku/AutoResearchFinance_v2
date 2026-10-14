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
