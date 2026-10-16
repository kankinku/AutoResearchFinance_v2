"""Generation durations are verified from real checkpoint transitions, not browser guesses."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.academic_run import create_academic_app
from tests.integrations.test_academic_mcp_sessions import _setup
from tests.research.test_autonomous_academic_cycle import ScriptedResearcher


def test_all_generation_durations_and_summary_after_verified_s7(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    root = tmp_path / 'state' / 'academic-gpt-checkpoints'
    sid = started['session_id']
    scripted = ScriptedResearcher()
    client = TestClient(create_academic_app(root))
    empty = client.get('/api/academic/overview').json()
    assert empty['timing']['measured_generations'] == 0
    assert empty['timing']['average_seconds'] is None
    assert empty['timing']['next_generation_eta_seconds'] is None
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': sid, 'checkpoint_token': started['checkpoint_token'],
        'plan': scripted.propose(started['model_context']),
    })
    assert staged['checkpoint_phase'] == 'AWAITING_DIAGNOSIS'
    pending = client.get('/api/academic/overview').json()['timing']
    assert pending['current_generation'] == 1
    assert pending['current_elapsed_seconds'] >= 0
    assert pending['next_generation_eta_seconds'] is None  # ChatGPT input required
    finished = server._dispatch('submit_algorithm_diagnosis', {
        'session_id': sid, 'checkpoint_token': staged['checkpoint_token'],
        'diagnosis': scripted.propose(staged['model_context']),
    })
    actual = client.get('/api/academic/overview').json()
    assert actual['completed'] == 1
    assert actual['timing']['measured_generations'] == 1
    assert actual['timing']['average_seconds'] >= 0
    assert actual['timing']['next_generation_eta_seconds'] is None
    assert actual['timing']['eta_reason'] == 'AWAITING_EXTERNAL_MODEL'
    assert actual['history'][0]['duration_seconds'] is not None
    assert actual['history'][0]['duration_seconds'] >= 0
    assert actual['history'][0]['timing_status'] == 'MEASURED'
    assert actual['latest_completed_model']['evidence_hash_prefix'] == (
        finished['history'][0]['evidence_hash'][:12]
    )
    with sqlite3.connect(root / 'gateway.sqlite') as db:
        query = (
            'SELECT start_utc, end_utc, evidence_hash FROM generation_timings '
            'WHERE session_id=? AND generation=1'
        )
        recorded = db.execute(query, (sid,)).fetchone()
        assert recorded and recorded[2] == finished['history'][0]['evidence_hash']
        # A duplicate replay must not reset timestamps.
        server._dispatch('evaluate_algorithm_experiments', {'session_id':sid,'generation':1})
        assert db.execute(query, (sid,)).fetchone() == recorded


def test_historical_generations_without_timestamps_are_not_fabricated(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    scripted = ScriptedResearcher()
    sid = started['session_id']
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': sid, 'checkpoint_token': started['checkpoint_token'],
        'plan': scripted.propose(started['model_context']),
    })
    server._dispatch('submit_algorithm_diagnosis', {
        'session_id': sid, 'checkpoint_token': staged['checkpoint_token'],
        'diagnosis': scripted.propose(staged['model_context']),
    })
    root = tmp_path / 'state' / 'academic-gpt-checkpoints'
    with sqlite3.connect(root/'gateway.sqlite') as db:
        db.execute('DELETE FROM generation_timings WHERE session_id=?',(sid,))
    result = TestClient(create_academic_app(root)).get('/api/academic/overview').json()
    assert result['timing']['measured_generations'] == 0
    assert result['history'][0]['duration_seconds'] is None
    assert result['history'][0]['timing_status'] == 'NOT_RECORDED'
    assert result['timing']['average_seconds'] is None


def test_corrupted_timing_evidence_is_rejected(tmp_path: Path) -> None:
    server, started = _setup(tmp_path)
    scripted = ScriptedResearcher()
    sid = started['session_id']
    staged = server._dispatch('submit_algorithm_plan', {
        'session_id': sid, 'checkpoint_token': started['checkpoint_token'],
        'plan': scripted.propose(started['model_context']),
    })
    server._dispatch('submit_algorithm_diagnosis', {
        'session_id': sid, 'checkpoint_token': staged['checkpoint_token'],
        'diagnosis': scripted.propose(staged['model_context']),
    })
    root = tmp_path / 'state' / 'academic-gpt-checkpoints'
    with sqlite3.connect(root / 'gateway.sqlite') as db:
        db.execute('UPDATE generation_timings SET evidence_hash=? WHERE session_id=?', ('f'*64,sid))
    response=TestClient(create_academic_app(root)).get('/api/academic/overview')
    assert response.status_code == 503
    assert response.json()['status']=='RESEARCH_STATE_UNAVAILABLE'
