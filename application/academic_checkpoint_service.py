"""Existing authenticated MCP resource: explicit GPT Plan→Audit→Diagnosis checkpoints.

The connected ChatGPT model is the Research Director. This service makes no
LLM HTTP calls and NEVER creates/rotates an MCP URL, OAuth record or key.
"""
from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from dataclasses import asdict
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
from research.indicator_engine.controlled_experiments import compare_controlled_experiments
from research.indicator_engine.external_reference import (
    audit_s6_external_reference,
    capture_s6_external_reference,
    get_s6_external_reference,
)
from research.indicator_engine.s6_seed import S6_SIGNALS, seed_s6_references
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.llm.adaptive_direction import build_research_direction
from research.llm.autonomous_cycle import AcademicCycleService, CycleStateError
from research.llm.diagnostic_research import build_diagnostic_context
from research.llm.execution_policy import research_execution_policy


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
        db.execute('''CREATE TABLE IF NOT EXISTS experiment_reports (
            session_id TEXT NOT NULL, generation INTEGER NOT NULL,
            report_json TEXT NOT NULL, report_hash TEXT NOT NULL,
            PRIMARY KEY(session_id, generation)
        )''')
        # Old sessions were created with the original catalog. Keep their
        # identity even after new S6 candidates become available.
        if 'catalog_version' not in {
            column['name'] for column in db.execute('PRAGMA table_info(stages)')
        }:
            db.execute(
                "ALTER TABLE stages ADD COLUMN catalog_version TEXT NOT NULL DEFAULT 's3-v1'"
            )
        return db

    def _catalog(self, version: str = 's3-v1') -> ResearchCatalog:
        if version not in ('s3-v1', 's6-v1', 's6-v2'):
            raise CycleStateError('unknown pinned research indicator catalog version')
        catalog_files = {
            's3-v1': 'catalog.sqlite',
            's6-v1': 'catalog-s6-v1.sqlite',
            's6-v2': 'catalog-s6-v2.sqlite',
        }
        catalog = ResearchCatalog(self.state / catalog_files[version])
        seed_approved_references(catalog)
        names: tuple[str, ...] = ('time_series_momentum', 'previous_range_breakout',
                 'parkinson_variance', 'sma_direction')
        if version in ('s6-v1', 's6-v2'):
            seed_s6_references(catalog)
            names += tuple(candidate.signal_id for candidate in S6_SIGNALS)
        s6_names = {candidate.signal_id for candidate in S6_SIGNALS}
        for name in names:
            indicator = catalog.get_indicator(name)
            if version == 's6-v2' and name in s6_names:
                evidence = get_s6_external_reference(catalog, name)
                if evidence is None:
                    # For a newly PROPOSED signal, require both reviewed
                    # math and pandas reference BEFORE promotion. A crash
                    # after promotion can backfill provenance without
                    # modifying the pinned indicator definition.
                    evidence = audit_s6_external_reference(indicator)
                    if indicator.status == 'PROPOSED':
                        catalog.verify_and_register(
                            name, verify_signal_on_synthetic_prices(indicator)
                        )
                    capture_s6_external_reference(catalog, evidence)
                if catalog.get_indicator(name).status != 'VERIFIED':
                    raise CycleStateError('S6 external reference not promoted')
            elif indicator.status == 'PROPOSED':
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
        catalog_version = 's6-v2'
        catalog = self._catalog(catalog_version)
        # Preserve existing replay, but reject newly started sessions after
        # the external provider has changed without a versioned review.
        from research.indicator_engine.external_reference import _backend_version
        current_version = _backend_version()
        for source in S6_SIGNALS:
            proof = get_s6_external_reference(catalog, source.signal_id)
            if proof is None or proof.version != current_version:
                raise CycleStateError('S6 reference backend version changed; new catalog required')
        started = self.cycle.start(catalog, data, generations=args['generations'])
        token = uuid4().hex
        sid = str(started['session_id'])
        with self._connect() as db:
            db.execute(
                'INSERT INTO stages(session_id,data_path,phase,token,catalog_version) '
                'VALUES(?,?,?,?,?)', (sid, path.relative_to(self.root).as_posix(),
                                     'AWAITING_PLAN', token, catalog_version),
            )
        return self.get({'session_id': sid})

    def _stored_experiment(
        self, db: sqlite3.Connection, sid: str, generation: int,
    ) -> dict[str, Any] | None:
        row = db.execute(
            'SELECT report_json,report_hash FROM experiment_reports '
            'WHERE session_id=? AND generation=?', (sid, generation),
        ).fetchone()
        if row is None:
            return None
        try:
            body = json.loads(row['report_json'])
        except ValueError as exc:
            raise CycleStateError('controlled experiment record integrity mismatch') from exc
        if not isinstance(body, dict) or content_hash(body) != row['report_hash']:
            raise CycleStateError('controlled experiment record integrity mismatch')
        return {**body, 'record_hash': row['report_hash']}

    def _context(
        self, catalog: ResearchCatalog, data: MarketDataSet, status: dict[str, Any],
    ) -> dict[str, Any]:
        context = build_algorithm_plan_context(catalog, data)
        context['generation'] = status['completed_generations'] + 1
        # Validate stored experiment checksum before it influences future LLM
        # direction. S7-v1 reports lack execution attribution and remain
        # readable, but cannot support the newer direction allocator.
        scored_reports: dict[int, dict[str, Any]] = {}
        with self._connect() as db:
            for item in status['history']:
                observed = self._stored_experiment(db, status['session_id'], item['generation'])
                if observed is not None and all(
                    'execution_delta' in experiment
                    for experiment in observed['report'].get('experiments', [])
                ):
                    scored_reports[item['generation']] = observed
        context['research_direction'] = build_research_direction(
            status['history'], scored_reports,
        )
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
            with self._connect() as db:
                measured = self._stored_experiment(
                    db, status['session_id'], previous['generation'],
                )
            if measured is not None:
                context['prior_research']['controlled_experiments'] = measured
        return context

    def _state(
        self, db: sqlite3.Connection, sid: str,
    ) -> tuple[sqlite3.Row, ResearchCatalog, MarketDataSet, dict[str, Any]]:
        row = db.execute('SELECT * FROM stages WHERE session_id=?', (sid,)).fetchone()
        if row is None:
            raise CycleStateError('unknown academic MCP session')
        catalog, data = self._catalog(row['catalog_version']), self._data(row['data_path'])
        return row, catalog, data, self.cycle.get(sid, catalog, data)

    def get(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(args, {'session_id'}, {'session_id'})
        sid = args['session_id']
        if not isinstance(sid, str) or len(sid) != 32:
            raise ValueError('session_id must be 32 hex characters')
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            result: dict[str, Any] = {**current, 'checkpoint_phase': row['phase'],
                                      'catalog_version': row['catalog_version'],
                                      'llm_controller': 'authenticated_chatgpt_mcp_client',
                                      'research_execution_policy': research_execution_policy(),
                                      'mcp_url_unchanged': True}
            if row['phase'] == 'AWAITING_PLAN':
                if current['status'] != 'AWAITING_PROVIDER':
                    raise CycleStateError('checkpoint phase mismatch')
                result['checkpoint_token'] = row['token']
                result['model_context'] = self._context(catalog, data, current)
                result['model_context']['catalog_version'] = row['catalog_version']
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
            elif row['phase'] not in ('COMPLETED', 'INTERRUPTED', 'RUNNING', 'CANCELLED'):
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
            catalog, data = self._catalog(row['catalog_version']), self._data(row['data_path'])
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
        # MCP-first shortcut: a complete research generation must carry its
        # measured experiment evidence into the NEXT LLM planning prompt.
        # Previously ChatGPT had to make an extra evaluate_* call and could
        # accidentally start the next generation from unmeasured hypotheses.
        # All comparison results use the existing immutable, idempotent S7
        # storage and the *same* development dataset as the original plan.
        measured_generation = completed['completed_generations']
        experiment_report = self.evaluate_experiments({
            'session_id': sid, 'generation': measured_generation,
        })
        refreshed = self.get({'session_id': sid})
        if (
            refreshed['completed_generations'] != measured_generation
            or experiment_report['original_generation_evidence_hash']
            != refreshed['history'][-1]['evidence_hash']
        ):
            raise CycleStateError('post-diagnosis experiment evidence mismatch')
        refreshed['latest_controlled_experiments'] = experiment_report
        refreshed['controlled_experiments_automatically_evaluated'] = True
        return refreshed

    def cancel(self, args: dict[str, Any]) -> dict[str, Any]:
        """Stop between generation checkpoints without losing prior Evidence."""
        self._one(args, {'session_id', 'checkpoint_token'},
                  {'session_id', 'checkpoint_token'})
        sid, token = args['session_id'], args['checkpoint_token']
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            if row['token'] != token:
                raise CycleStateError('invalid checkpoint token')
            if row['phase'] not in ('AWAITING_PLAN', 'AWAITING_DIAGNOSIS', 'INTERRUPTED'):
                raise CycleStateError('cancel only at a safe checkpoint')
            if current['status'] not in ('AWAITING_PROVIDER', 'INTERRUPTED'):
                raise CycleStateError('cancel requires a stable checkpoint')
            self.cycle.cancel(sid, catalog, data)
            changed = db.execute(
                "UPDATE stages SET phase='CANCELLED',plan_json=NULL,"
                "plan_digest=NULL,context_digest=NULL,token=? "
                "WHERE session_id=? AND token=?",
                (uuid4().hex, sid, token),
            )
            if changed.rowcount != 1:
                raise CycleStateError('cancel checkpoint conflict')
        return self.get({'session_id': sid})

    def reconcile(self, args: dict[str, Any]) -> dict[str, Any]:
        """Operator-triggered reconciliation after an interrupted server process."""
        self._one(args, {'session_id'}, {'session_id'})
        sid = args['session_id']
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            if row['phase'] != 'RUNNING':
                raise CycleStateError('reconcile only stalled running gateway checkpoint')
            cycle_status = current['status']
            if cycle_status == 'EXECUTING':
                self.cycle.interrupt_stale(sid, catalog, data)
                phase = 'INTERRUPTED'
            elif cycle_status == 'INTERRUPTED':
                phase = 'INTERRUPTED'
            elif cycle_status == 'COMPLETED':
                phase = 'COMPLETED'
            elif cycle_status == 'AWAITING_PROVIDER':
                phase = 'AWAITING_PLAN'
            else:
                raise CycleStateError('inconsistent checkpoint cannot be reconciled')
            changed = db.execute(
                'UPDATE stages SET phase=?,token=?,plan_json=NULL,'
                'plan_digest=NULL,context_digest=NULL '
                "WHERE session_id=? AND phase='RUNNING'",
                (phase, uuid4().hex, sid),
            )
            if changed.rowcount != 1:
                raise CycleStateError('concurrent gateway checkpoint change')
        return self.get({'session_id': sid})

    def evaluate_experiments(self, args: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a completed diagnosis against its frozen original strategy."""
        self._one(args, {'session_id', 'generation'}, {'session_id', 'generation'})
        sid, generation = args['session_id'], args['generation']
        if type(generation) is not int or not 1 <= generation <= 100:
            raise ValueError('generation must be integer 1-100')
        with self._connect() as db:
            _, catalog, data, state = self._state(db, sid)
            if generation > state['completed_generations']:
                raise ValueError('generation is not complete')
            stored = self._stored_experiment(db, sid, generation)
            if stored is not None:
                if stored['original_generation_evidence_hash'] != state['history'][
                    generation - 1
                ]['evidence_hash']:
                    raise CycleStateError('controlled experiment parent evidence mismatch')
                return stored
        original = state['history'][generation - 1]
        plan = AlgorithmPlan.model_validate(original['algorithm_plan'])
        compiled = compile_algorithm_plan(catalog, plan, data)
        if compiled.compiled.strategy_hash != original['strategy_hash']:
            raise CycleStateError('original strategy hash mismatch')
        hypotheses = [
            {
                'hypothesis_id': item['hypothesis_id'],
                'observed_ids': item['observed_ids'],
                'mechanism': item['mechanism'],
                'alternative': item['alternative'],
                'expected_metric': item['expected_metric'],
                'predicted_direction': item['predicted_direction'],
                'test_design': item['test_design'],
                'control': item['control'],
                'next_intent': item['proposed_intent'],
            }
            for item in original['experiments']
        ]
        diagnostic = {
            'context_hash': original['diagnostic_context_hash'],
            'audit_hash': original['audit_hash'],
            'strategy_hash': original['strategy_hash'],
            'dataset_hash': original['dataset_hash'],
            'summary': original['analysis_summary'],
            'hypotheses': hypotheses,
        }
        report = compare_controlled_experiments(catalog, compiled, data, diagnostic)
        if (
            report.diagnostic_proposal_hash != original['diagnostic_proposal_hash']
            or report.audit_hash != original['audit_hash']
            or report.plan_hash != original['plan_hash']
        ):
            raise CycleStateError('controlled experiment does not match original evidence')
        body = {
            'session_id': sid,
            'generation': generation,
            'original_generation_evidence_hash': original['evidence_hash'],
            'report': asdict(report),
            'study_scope': 'REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF',
        }
        digest = content_hash(body)
        with self._connect() as db:
            db.execute(
                'INSERT OR IGNORE INTO experiment_reports '
                '(session_id,generation,report_json,report_hash) VALUES(?,?,?,?)',
                (sid, generation, json.dumps(body, sort_keys=True), digest),
            )
            verified = self._stored_experiment(db, sid, generation)
            if verified is None:
                raise CycleStateError('controlled experiment persistence failed')
            if verified['original_generation_evidence_hash'] != original['evidence_hash']:
                raise CycleStateError('controlled experiment concurrent identity mismatch')
            return verified

    def resume(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(args, {'session_id'}, {'session_id'})
        sid = args['session_id']
        with self._connect() as db:
            row,catalog,data,current = self._state(db,sid)
            if row['phase'] != 'INTERRUPTED' or current['status'] not in (
                'INTERRUPTED', 'AWAITING_PROVIDER',
            ):
                raise CycleStateError('only interrupted academic MCP sessions can resume')
            if current['status'] == 'INTERRUPTED':
                self.cycle.resume(sid,catalog,data)
            db.execute('''UPDATE stages SET phase='AWAITING_PLAN',token=?,plan_json=NULL,
            plan_digest=NULL,context_digest=NULL WHERE session_id=? AND phase='INTERRUPTED' ''',
                       (uuid4().hex,sid))
        return self.get({'session_id':sid})
