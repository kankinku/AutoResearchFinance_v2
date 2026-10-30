"""Guided now learns from ALL development outcomes, not only winners."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

import pytest

from application.gpt_guided_research_service import GPTGuidedResearchService
from core.integrity.hashes import content_hash
from integrations.chatgpt_mcp_sdk import chatgpt_tools
from memory.evidence_store import EvidenceStore
from research.llm.guided_research_feedback import (
    check_proposal, summarize, training_outcome,
)


def _fixture(tmp_path):
    root=Path(__file__).resolve().parents[2]
    service=GPTGuidedResearchService(project_root=root,state_dir=tmp_path/'independent_state')
    source='strategies/normalized/0a805e67c88e16da-4.json'
    dataset='data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet'
    p=service.start({'data_path':dataset,'generations':2,'count':1,'seed':987654,
                     'require_execution_change':True,'allow_research_parent_inheritance':True,
                     'benchmark_mode':'QQQ_COSTED_NEXT_OPEN_DEV_V1'})
    return service,p,source


def _intent(size, parent_id='golden_cross'):
    return {'mode':'mixed','parent_ids':[parent_id],
            'rationale':'costed development research single size controlled mutation',
            'operations':[{'op':'SET_PARAMETER','path':'risk.position_size_pct',
                           'value':float(size)}]}


def _submit(service,point,source,size,**extra):
    return service.submit({'session_id':point['session_id'],
        'checkpoint_token':point['checkpoint_token'],'generation':point['generation'],
        'source_path':source,'intent':_intent(size),**extra})


def test_failed_candidate_can_be_reused_as_development_parent_without_promotion(tmp_path):
    service,point,source=_fixture(tmp_path)
    first=_submit(service,point,source,90)
    feedback=first['learning_feedback']
    assert first['completed_generations']==1
    assert feedback['evaluated_candidates']==1
    assert feedback['failed_candidates_included']==1
    assert feedback['production_promotions']==0
    assert feedback['never_use_validation_or_oos_for_parent_ranking']
    assert feedback['development_research_parent_shortlist']
    assert feedback['development_research_parent_shortlist'][0]['generation']==1
    assert feedback['recent_observations'][0]['failed_gates']
    run_id=first['last_run_id']
    with sqlite3.connect(service.db_path) as db:
        row=db.execute('SELECT proposal_json,proposal_hash,status FROM guided_research_proposals WHERE run_id=?',(run_id,)).fetchone()
    proposal=json.loads(row[0]);assert row[2]=='COMMITTED'
    assert check_proposal(proposal,expected_hash=row[1])['generation']==1
    assert content_hash(proposal)==row[1]
    saved=[e for e in EvidenceStore(service.state_dir).events()
           if e['kind']=='run' and e['payload']['research_run_id']==run_id][0]
    assert saved['payload']['settings']['guided_proposal_hash']==row[1]
    second=_submit(service,first,source,75,research_parent_generation=1)
    assert second['status']=='COMPLETED' and second['completed_generations']==2
    assert second['learning_feedback']['evaluated_candidates']==2
    assert second['learning_feedback']['failed_candidates_included']==2
    assert second['learning_feedback']['production_promotions']==0
    run2=second['last_run_id']
    proof=[e['payload'] for e in EvidenceStore(service.state_dir).events()
           if e['kind']=='run' and e['payload']['research_run_id']==run2][0]
    assert proof['settings']['inherited_parent_run_id']==run_id
    assert proof['settings']['inherited_parent_semantic_hash']==proposal['candidates'][0]['semantic_strategy_hash']
    assert second['sealed_oos_evaluated'] is False and second['orders_enabled'] is False


def test_research_parent_requires_opt_in_and_strict_execution(tmp_path):
    service,point,source=_fixture(tmp_path)
    no_policy=service.start({'data_path':'data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet',
             'generations':2,'require_execution_change':True})
    with pytest.raises(ValueError,match='SESSION_OPT_IN_REQUIRED'):
        _submit(service,no_policy,source,90,research_parent_generation=1)
    with pytest.raises(ValueError,match='requires strict execution'):
        service.start({'data_path':'data/market/public_yahoo_qqq/QQQ_2020-01-02_2025-12-31_raw.parquet',
                       'generations':2,'allow_research_parent_inheritance':True})
    with pytest.raises(ValueError,match='MUST_BE_PRIOR_GENERATION'):
        _submit(service,point,source,90,research_parent_generation=1)
    assert service.get(point['session_id'])['completed_generations']==0


def test_signed_proposal_tampering_fails_closed(tmp_path):
    service,point,source=_fixture(tmp_path)
    first=_submit(service,point,source,90)
    run=first['last_run_id']
    with sqlite3.connect(service.db_path) as db:
        db.execute('UPDATE guided_research_proposals SET proposal_json=? WHERE run_id=?',
                   ('{"changed":"unverified"}',run))
    with pytest.raises(ValueError,match='GUIDED_PROPOSAL_HASH_MISMATCH'):
        service.get(first['session_id'])
    assert len([e for e in EvidenceStore(service.state_dir).events() if e['kind']=='attempt'])==1


def test_feedback_keeps_failed_outcomes_and_train_only_rank_in_isolation():
    def make(i,failed,train):
        return {'run_id':f'run{i}','attempt_id':f'attempt{i}',
                'proposal_verified':True,'proposal_hash':f'proof{i}',
                'attempt':{'status':'COMPLETED','verification':None,
                  'research_run_id':f'run{i}','attempt_id':f'attempt{i}',
                  'train_only_selection':{'sealed_oos_evaluated':False,
                     'upstream_selection_verified':False,
                     'folds':[{'selected_candidate_hash':f'cand{i}',
                               'train_total_return':train,
                               'test_total_return':9999 if i==1 else -9999,
                               'selection_applied':True,
                               'train_end_at':'2022-12-01','test_start_at':'2023-01-01'}]},
                  'candidates':[{'candidate_hash':f'cand{i}',
                      'dataset_hash':'pinned','semantic_strategy_hash':f'sem{i}',
                      'failed_gates':failed,'family':'trend',
                      'status':'REJECT' if failed else 'SURVIVOR',
                      'full_cagr':100 if i==1 else -100,
                      'max_drawdown':0.1,'trade_count':40,
                      'qqq_cagr_delta':-1 if i==1 else 1}]} }
    result=summarize([make(1,['validation','qqq_cagr_delta'],.1),
                      make(2,['annual_trade_count'],.4)],dataset_hash='pinned')
    assert result['failed_candidates_included']==2
    assert result['development_research_parent_shortlist'][0]['generation']==2
    assert result['failure_gate_counts']['validation']==1
    assert result['failure_gate_counts']['annual_trade_count']==1
    assert result['production_promotions']==0


def test_mcp_contract_exposes_learning_and_research_parent_without_new_url_or_tools():
    catalog={r['name']:r for r in chatgpt_tools()}
    assert len(catalog)==33
    assert catalog['start_guided_research']['inputSchema']['properties']['allow_research_parent_inheritance']['default'] is False
    assert 'research_parent_generation' in catalog['submit_guided_generation']['inputSchema']['properties']
    assert 'feedback' in catalog['get_guided_research']['description'].lower()
