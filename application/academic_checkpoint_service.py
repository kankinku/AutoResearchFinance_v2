"""Existing authenticated MCP resource: explicit GPT Plan→Audit→Diagnosis checkpoints.

The connected ChatGPT model is the Research Director. This service makes no
LLM HTTP calls and NEVER creates/rotates an MCP URL, OAuth record or key.
"""
from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.data.contracts import MarketDataSet
from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash
from orchestration.evaluation_runner import resolve_project_input
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    build_algorithm_plan_context,
    compile_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.llm.autonomous_cycle import AcademicCycleService, CycleStateError
from research.llm.diagnostic_research import build_diagnostic_context


class _SubmittedProvider:
    """Transport for independently GPT-authored, immutable staged responses."""

    def __init__(self, plan: dict[str, Any], diagnosis: dict[str, Any]):
        self.plan = plan
        self.diagnosis = diagnosis
        self.seen = 0

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        self.seen += 1
        if self.seen == 1 and context.get('output_contract') == 'AlgorithmPlan':
            return deepcopy(self.plan)
        if self.seen == 2 and context.get('schema') == 'research-diagnostic-context-v1':
            if self.diagnosis.get('context_hash') != context.get('context_hash'):
                raise CycleStateError('diagnostic context changed after GPT saw it')
            return deepcopy(self.diagnosis)
        raise CycleStateError('unexpected research phase or duplicate provider call')


class AcademicMCPCheckpointService:
    """Binds external ChatGPT proposals to frozen, persistent research input state."""

    def __init__(self, *, project_root: Path, state_dir: Path):
        self.root = project_root.resolve()
        self.state = state_dir.resolve() / 'academic-gpt-checkpoints'
        self.cycle = AcademicCycleService(self.state / 'cycles.sqlite')

    def _connect(self) -> sqlite3.Connection:
        self.state.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.state / 'gateway.sqlite', timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=30000')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS stages (
          session_id TEXT PRIMARY KEY, data_path TEXT NOT NULL,
          phase TEXT NOT NULL, token TEXT NOT NULL,
          plan_json TEXT, plan_digest TEXT, context_digest TEXT
        )''')
        return db

    def _catalog(self) -> ResearchCatalog:
        catalog = ResearchCatalog(self.state / 'catalog.sqlite')
        seed_approved_references(catalog)
        for name in ('time_series_momentum', 'previous_range_breakout',
                     'parkinson_variance', 'sma_direction'):
            indicator = catalog.get_indicator(name)
            if indicator.status == 'PROPOSED':
                catalog.verify_and_register(name, verify_signal_on_synthetic_prices(indicator))
        return catalog

    def _data(self, path: str) -> MarketDataSet:
        return ParquetDataProvider.read(resolve_project_input(
            self.root, path, frozenset({'.parquet'})
        ))

    @staticmethod
    def _one(
        args: dict[str, Any], allowed: set[str], required: set[str],
    ) -> None:
        if set(args) - allowed or not required <= set(args):
            raise ValueError('unexpected or missing academic checkpoint arguments')

    def start(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(args, {'data_path', 'generations'}, {'data_path', 'generations'})
        if type(args['generations']) is not int or not 1 <= args['generations'] <= 100:
            raise ValueError('generations must be integer 1..100')
        if not isinstance(args['data_path'], str):
            raise ValueError('data_path must be a string')
        path = resolve_project_input(self.root, args['data_path'], frozenset({'.parquet'}))
        data = ParquetDataProvider.read(path)
        catalog = self._catalog()
        started = self.cycle.start(catalog, data, generations=args['generations'])
        token = uuid4().hex
        sid = str(started['session_id'])
        with self._connect() as db:
            db.execute('INSERT INTO stages(session_id,data_path,phase,token) '
                       'VALUES(?,?,?,?)', (sid, path.relative_to(self.root).as_posix(),
                                          'AWAITING_PLAN', token))
        return self.get({'session_id': sid})

    def _context(
        self, catalog: ResearchCatalog, data: MarketDataSet, status: dict[str, Any],
    ) -> dict[str, Any]:
        context = build_algorithm_plan_context(catalog, data)
        context['generation'] = status['completed_generations'] + 1
        if status['history']:
            previous = status['history'][-1]
            context['prior_research'] = {
                'generation': previous['generation'],
                'evidence_hash': previous['evidence_hash'],
                'audit_hash': previous['audit_hash'],
                'diagnostic_proposal_hash': previous['diagnostic_proposal_hash'],
                'causal_status': previous['causal_status'],
                'analysis_summary': previous['analysis_summary'],
                'experiments': previous['experiments'],
                'metrics': previous['metrics'],
                'prior_algorithm_semantic_hash': previous['algorithm_semantic_hash'],
            }
        return context

    def _state(
        self, db: sqlite3.Connection, sid: str,
    ) -> tuple[sqlite3.Row, ResearchCatalog, MarketDataSet, dict[str, Any]]:
        row = db.execute('SELECT * FROM stages WHERE session_id=?', (sid,)).fetchone()
        if row is None:
            raise CycleStateError('unknown academic MCP session')
        catalog, data = self._catalog(), self._data(row['data_path'])
        return row, catalog, data, self.cycle.get(sid, catalog, data)

    def get(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(args, {'session_id'}, {'session_id'})
        sid = args['session_id']
        if not isinstance(sid, str) or len(sid) != 32:
            raise ValueError('session_id must be 32 hex characters')
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            result: dict[str, Any] = {**current, 'checkpoint_phase': row['phase'],
                                      'llm_controller': 'authenticated_chatgpt_mcp_client',
                                      'mcp_url_unchanged': True}
            if row['phase'] == 'AWAITING_PLAN':
                if current['status'] != 'AWAITING_PROVIDER':
                    raise CycleStateError('checkpoint phase mismatch')
                result['checkpoint_token'] = row['token']
                result['model_context'] = self._context(catalog, data, current)
            elif row['phase'] == 'AWAITING_DIAGNOSIS':
                if current['status'] != 'AWAITING_PROVIDER':
                    raise CycleStateError('checkpoint phase mismatch')
                pending = json.loads(row['plan_json'])
                plan = AlgorithmPlan.model_validate(pending)
                compiled = compile_algorithm_plan(catalog, plan, data)
                if content_hash(pending) != row['plan_digest']:
                    raise CycleStateError('pending algorithm integrity mismatch')
                audit = audit_algorithm_plan(catalog, compiled, data)
                context = build_diagnostic_context(audit, compiled.compiled.strategy)
                if context['context_hash'] != row['context_digest']:
                    raise CycleStateError('pending analysis integrity mismatch')
                result['checkpoint_token'] = row['token']
                result['model_context'] = context
                result['status'] = 'AWAITING_DIAGNOSIS'
            elif row['phase'] not in ('COMPLETED', 'INTERRUPTED', 'RUNNING'):
                raise CycleStateError('invalid checkpoint state')
            return result

    def submit_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(args, {'session_id', 'checkpoint_token', 'plan'},
                  {'session_id', 'checkpoint_token', 'plan'})
        sid, token = args['session_id'], args['checkpoint_token']
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            if row['phase'] != 'AWAITING_PLAN' or current['status'] != 'AWAITING_PROVIDER':
                raise CycleStateError('plan cannot be submitted in current state')
            if row['token'] != token:
                raise CycleStateError('invalid checkpoint token')
            plan = AlgorithmPlan.model_validate(args['plan'])
            compiled = compile_algorithm_plan(catalog, plan, data)
            audit = audit_algorithm_plan(catalog, compiled, data)
            context = build_diagnostic_context(audit, compiled.compiled.strategy)
            pending = plan.model_dump(mode='json')
            new_token = uuid4().hex
            result = db.execute(
                '''UPDATE stages SET phase='AWAITING_DIAGNOSIS',token=?,plan_json=?,
                plan_digest=?,context_digest=? WHERE session_id=? AND phase='AWAITING_PLAN'
                AND token=?''',
                (new_token, json.dumps(pending,sort_keys=True),content_hash(pending),
                 context['context_hash'],sid,token),
            )
            if result.rowcount != 1:
                raise CycleStateError('concurrent plan checkpoint was claimed')
        return self.get({'session_id': sid})

    def submit_diagnosis(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(args, {'session_id','checkpoint_token','diagnosis'},
                  {'session_id','checkpoint_token','diagnosis'})
        sid, token, diagnosis = args['session_id'], args['checkpoint_token'], args['diagnosis']
        if not isinstance(diagnosis, dict):
            raise ValueError('diagnosis must be a structured object')
        # Recompute all observed evidence before any generation can be committed.
        pending = self.get({'session_id': sid})
        if (pending['checkpoint_phase'] != 'AWAITING_DIAGNOSIS'
                or pending['checkpoint_token'] != token):
            raise CycleStateError('invalid diagnosis checkpoint token or state')
        if diagnosis.get('context_hash') != pending['model_context']['context_hash']:
            raise CycleStateError('invalid diagnosis context hash')
        with self._connect() as db:
            row = db.execute('SELECT * FROM stages WHERE session_id=?', (sid,)).fetchone()
            assert row is not None
            updated = db.execute(
                "UPDATE stages SET phase='RUNNING' WHERE session_id=? "
                "AND phase='AWAITING_DIAGNOSIS' AND token=?",
                (sid, token),
            )
            if updated.rowcount != 1:
                raise CycleStateError('concurrent diagnosis checkpoint was claimed')
            catalog, data = self._catalog(), self._data(row['data_path'])
            plan_json = json.loads(row['plan_json'])
        try:
            completed = self.cycle.advance(sid, catalog, data,
                                           _SubmittedProvider(plan_json, diagnosis))
        except Exception:
            with self._connect() as db:
                db.execute(
                    "UPDATE stages SET phase='INTERRUPTED' "
                    "WHERE session_id=? AND phase='RUNNING'", (sid,),
                )
            raise
        with self._connect() as db:
            db.execute('''UPDATE stages SET phase=?,token=?,plan_json=NULL,
            plan_digest=NULL,context_digest=NULL WHERE session_id=? AND phase='RUNNING' ''',
            ('COMPLETED' if completed['status']=='COMPLETED' else 'AWAITING_PLAN',uuid4().hex,sid))
        return self.get({'session_id': sid})

    def resume(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(args, {'session_id'}, {'session_id'})
        sid = args['session_id']
        with self._connect() as db:
            row,catalog,data,current = self._state(db,sid)
            if row['phase'] != 'INTERRUPTED' or current['status'] != 'INTERRUPTED':
                raise CycleStateError('only interrupted academic MCP sessions can resume')
            self.cycle.resume(sid,catalog,data)
            db.execute('''UPDATE stages SET phase='AWAITING_PLAN',token=?,plan_json=NULL,
            plan_digest=NULL,context_digest=NULL WHERE session_id=? AND phase='INTERRUPTED' ''',
                       (uuid4().hex,sid))
        return self.get({'session_id':sid})
