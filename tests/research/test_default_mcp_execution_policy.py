"""MCP is the default even if a separate paid API key exists."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from integrations.codex_mcp_core import create_mcp_server
from research.llm.execution_policy import (
    DEFAULT_RESEARCH_EXECUTION_MODE,
    research_execution_policy,
)
from scripts import run_academic_autopilot as cli


def test_project_policy_defaults_to_existing_mcp_and_never_paid_api():
    assert DEFAULT_RESEARCH_EXECUTION_MODE == 'mcp'
    rules = research_execution_policy()
    assert rules['default_mode'] == 'mcp'
    assert rules['default_controller'] == 'authenticated_chatgpt_mcp_client'
    assert rules['default_requires_openai_api_key'] is False
    assert rules['model_api_auto_enabled'] is False
    assert rules['model_api_explicit_opt_in_required'] is True
    assert rules['orders_enabled'] is False
    assert {'start_algorithm_research', 'submit_algorithm_plan',
            'submit_algorithm_diagnosis', 'evaluate_algorithm_experiments'} <= set(
                rules['mcp_research_tools']
            )
    rules['default_mode'] = 'openai-api'
    assert research_execution_policy()['default_mode'] == 'mcp'


def test_authenticated_mcp_brief_advertises_existing_default_without_changing_tools(
    tmp_path: Path,
):
    server = create_mcp_server(project_root=tmp_path, state_dir=tmp_path / 'state')
    brief = server._dispatch('get_research_brief', {})
    assert brief['llm_controller'] == 'external_mcp_client'
    assert brief['research_execution_policy']['default_mode'] == 'mcp'
    assert brief['research_execution_policy']['model_api_auto_enabled'] is False
    assert brief['mcp_capabilities']['server_tool_count'] == 32
    assert not (tmp_path / 'state').exists()


def test_cli_defaults_mcp_even_with_api_key_and_never_creates_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-exists-but-must-be-ignored')

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError('MCP default must not create session or external model')

    monkeypatch.setattr(cli, 'AcademicMCPCheckpointService', forbidden)
    monkeypatch.setattr(cli, 'OpenAIResponsesResearcher', forbidden)
    monkeypatch.setattr(sys, 'argv', [
        'run_academic_autopilot.py', '--project-root', str(tmp_path / 'project'),
        '--state-dir', str(tmp_path / 'state'),
        '--data-path', 'data/study.parquet', '--generations', '10',
    ])
    cli.main()
    outcome = json.loads(capsys.readouterr().out)
    assert outcome['execution_mode'] == 'mcp'
    assert outcome['session_created'] is False
    assert outcome['external_model_called'] is False
    assert outcome['status'] == 'USE_EXISTING_CHATGPT_MCP_CONNECTOR'
    assert not (tmp_path / 'state').exists()
    assert not (tmp_path / 'project').exists()


def test_cli_requires_explicit_api_optin_even_if_model_argument_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    monkeypatch.setattr(sys, 'argv', [
        'run_academic_autopilot.py', '--project-root', str(tmp_path),
        '--state-dir', str(tmp_path / 'state'), '--model', 'gpt-5.5',
        '--data-path', 'data/study.parquet',
    ])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert not (tmp_path / 'state').exists()


def test_api_optin_requires_model_then_key_and_never_silently_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    monkeypatch.setenv('OPENAI_API_KEY', 'fake')
    args = [
        'run_academic_autopilot.py', '--project-root', str(tmp_path),
        '--state-dir', str(tmp_path / 'state'),
        '--data-path', 'data/study.parquet',
        '--execution-mode', 'openai-api',
    ]
    monkeypatch.setattr(sys, 'argv', args)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    monkeypatch.delenv('OPENAI_API_KEY')
    monkeypatch.setattr(sys, 'argv', args + ['--model', 'gpt-5.5'])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert not (tmp_path / 'state').exists()


def test_mcp_existing_session_preflight_is_read_only_and_never_uses_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setenv('OPENAI_API_KEY', 'present-but-must-not-be-used')

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError('preflight must never call a provider or write session')

    monkeypatch.setattr(cli, 'OpenAIResponsesResearcher', forbidden)
    monkeypatch.setattr(cli, 'AcademicMCPCheckpointService', forbidden)
    sid = 'd' * 32
    monkeypatch.setattr(sys, 'argv', [
        'run_academic_autopilot.py', '--project-root', str(tmp_path / 'project'),
        '--state-dir', str(tmp_path / 'state'), '--session-id', sid,
    ])
    cli.main()
    body = json.loads(capsys.readouterr().out)
    assert body['session_created'] is False
    assert body['external_model_called'] is False
    assert body['model_execution_possible_without_host'] is False
    assert body['status'] == 'RESEARCH_STATE_UNAVAILABLE'
    assert 'start_algorithm_research' not in body['next_step']
    assert 'replacement session' in body['next_step']
    assert 'checkpoint_token' not in body
    assert not (tmp_path / 'state').exists()


def test_paid_api_mode_requires_explicit_proposal_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    monkeypatch.setenv('OPENAI_API_KEY', 'present-but-must-not-be-used')
    monkeypatch.setattr(cli, 'OpenAIResponsesResearcher', lambda **kw: pytest.fail(
        'model provider constructed before budget validation'))
    monkeypatch.setattr(sys, 'argv', [
        'run_academic_autopilot.py', '--project-root', str(tmp_path),
        '--state-dir', str(tmp_path / 'state'), '--session-id', 'd' * 32,
        '--execution-mode', 'openai-api', '--model', 'explicit-model',
    ])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert not (tmp_path / 'state').exists()
