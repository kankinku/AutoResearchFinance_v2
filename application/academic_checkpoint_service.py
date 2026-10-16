"""Existing authenticated MCP resource: explicit GPT Plan→Audit→Diagnosis checkpoints.

The connected ChatGPT model is the Research Director. This service makes no
LLM HTTP calls and NEVER creates/rotates an MCP URL, OAuth record or key.
"""
from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
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
from research.indicator_engine.controlled_experiments import (
    SUPPORTED_CONTROLLED_METRICS,
    compare_controlled_experiments,
)
from research.indicator_engine.experiment_preflight import (
    academic_diagnostic_quality_hint,
    static_noop_hypotheses,
)
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
from research.llm.diagnostic_research import DiagnosticResponse, build_diagnostic_context
from research.llm.execution_policy import research_execution_policy
from research.llm.experiment_learning import build_experiment_learning


class DuplicateAlgorithmPlanError(ValueError):
    """A known proposal conflict; no stage or checkpoint token was consumed."""

    def __init__(self, code: str, previous_generation: int) -> None:
        if code not in ("DUPLICATE_SEMANTIC_PLAN", "DUPLICATE_EFFECTIVE_SIGNALS"):
            raise ValueError("invalid duplicate-plan reason")
        self.code = code
        self.previous_generation = previous_generation
        super().__init__(
            f"{code}: previously tested generation {previous_generation}; "
            "revise the plan and resubmit using the same checkpoint token"
        )


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
        # Supplemental wall-clock observation; no changes to canonical evidence hashes.
        db.execute('''CREATE TABLE IF NOT EXISTS generation_timings (
            session_id TEXT NOT NULL, generation INTEGER NOT NULL,
            start_utc TEXT NOT NULL, end_utc TEXT, evidence_hash TEXT,
            PRIMARY KEY(session_id, generation)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS experiment_reports (
            session_id TEXT NOT NULL, generation INTEGER NOT NULL,
            report_json TEXT NOT NULL, report_hash TEXT NOT NULL,
            PRIMARY KEY(session_id, generation)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS submission_receipts (
            session_id TEXT NOT NULL, kind TEXT NOT NULL,
            submitted_token_hash TEXT NOT NULL, request_hash TEXT NOT NULL,
            resulting_token_hash TEXT NOT NULL, resulting_phase TEXT NOT NULL,
            completed_generations INTEGER NOT NULL, receipt_hash TEXT NOT NULL,
            PRIMARY KEY(session_id, kind)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS recovery_receipts (
            session_id TEXT NOT NULL, action TEXT NOT NULL,
            result_phase TEXT NOT NULL, result_token_hash TEXT NOT NULL,
            completed_generations INTEGER NOT NULL, receipt_hash TEXT NOT NULL,
            PRIMARY KEY(session_id, action)
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

    @staticmethod
    def _record_submission(
        db: sqlite3.Connection, sid: str, kind: str, submitted_token: str,
        request: object, resulting_token: str, resulting_phase: str,
        completed_generations: int,
    ) -> None:
        """Persist a single most-recent receipt without storing secret tokens."""
        body = {
            'session_id': sid, 'kind': kind,
            'submitted_token_hash': content_hash(submitted_token),
            'request_hash': content_hash(request),
            'resulting_token_hash': content_hash(resulting_token),
            'resulting_phase': resulting_phase,
            'completed_generations': completed_generations,
        }
        db.execute(
            "INSERT INTO submission_receipts VALUES(?,?,?,?,?,?,?,?) "
            "ON CONFLICT(session_id,kind) DO UPDATE SET "
            "submitted_token_hash=excluded.submitted_token_hash, "
            "request_hash=excluded.request_hash, "
            "resulting_token_hash=excluded.resulting_token_hash, "
            "resulting_phase=excluded.resulting_phase, "
            "completed_generations=excluded.completed_generations, "
            "receipt_hash=excluded.receipt_hash",
            (*body.values(), content_hash(body)),
        )

    @staticmethod
    def _is_recent_replay(
        db: sqlite3.Connection, row: sqlite3.Row, current: dict[str, Any],
        kind: str, submitted_token: str, request: object,
    ) -> bool:
        """Only replay the last identical acknowledged step at the same checkpoint."""
        receipt = db.execute(
            'SELECT * FROM submission_receipts WHERE session_id=? AND kind=?',
            (row['session_id'], kind),
        ).fetchone()
        if receipt is None:
            return False
        body = {key: receipt[key] for key in (
            'session_id', 'kind', 'submitted_token_hash', 'request_hash',
            'resulting_token_hash', 'resulting_phase', 'completed_generations',
        )}
        if content_hash(body) != receipt['receipt_hash']:
            raise CycleStateError('submission receipt integrity failure')
        if receipt['submitted_token_hash'] != content_hash(submitted_token):
            return False
        if receipt['request_hash'] != content_hash(request):
            raise CycleStateError('conflicting replay payload for consumed checkpoint token')
        if (row['phase'] != receipt['resulting_phase']
                or content_hash(row['token']) != receipt['resulting_token_hash']
                or current['completed_generations'] != receipt['completed_generations']):
            raise CycleStateError('stale replay after checkpoint advanced')
        return True

    def _evaluated_reply(self, sid: str, generation: int) -> dict[str, Any]:
        """Reconstruct the two-write reply, including immutable S7 evidence."""
        experiment_report = self.evaluate_experiments({
            'session_id': sid, 'generation': generation,
        })
        refreshed = self.get({'session_id': sid})
        if (
            refreshed['completed_generations'] != generation
            or experiment_report['original_generation_evidence_hash']
            != refreshed['history'][-1]['evidence_hash']
        ):
            raise CycleStateError('post-diagnosis experiment evidence mismatch')
        refreshed['latest_controlled_experiments'] = experiment_report
        refreshed['controlled_experiments_automatically_evaluated'] = True
        return refreshed

    @staticmethod
    def _store_recovery_receipt(
        db: sqlite3.Connection, sid: str, action: str, phase: str,
        token: str, completed_generations: int,
    ) -> None:
        """Record one completed recovery action; never retain the raw token."""
        body = {
            'session_id': sid, 'action': action, 'result_phase': phase,
            'result_token_hash': content_hash(token),
            'completed_generations': completed_generations,
        }
        db.execute(
            "INSERT INTO recovery_receipts VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(session_id,action) DO UPDATE SET "
            "result_phase=excluded.result_phase,"
            "result_token_hash=excluded.result_token_hash,"
            "completed_generations=excluded.completed_generations,"
            "receipt_hash=excluded.receipt_hash",
            (*body.values(), content_hash(body)),
        )

    @staticmethod
    def _is_recovery_replay(
        db: sqlite3.Connection, row: sqlite3.Row,
        current: dict[str, Any], action: str,
    ) -> bool:
        """Only accept a repeat while the exact recovered checkpoint survives."""
        receipt = db.execute(
            'SELECT * FROM recovery_receipts WHERE session_id=? AND action=?',
            (row['session_id'], action),
        ).fetchone()
        if receipt is None:
            return False
        body = {name: receipt[name] for name in (
            'session_id', 'action', 'result_phase', 'result_token_hash',
            'completed_generations',
        )}
        if content_hash(body) != receipt['receipt_hash']:
            raise CycleStateError('recovery receipt integrity failure')
        return bool(
            receipt['result_phase'] == row['phase']
            and receipt['result_token_hash'] == content_hash(row['token'])
            and receipt['completed_generations'] == current['completed_generations']
        )

    def _recovery_reply(
        self, sid: str, generations: int,
    ) -> dict[str, Any]:
        """Require S7 provenance for any exposed recovered completed generation."""
        if generations == 0:
            return self.get({'session_id': sid})
        return self._evaluated_reply(sid, generations)

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
        # Regenerate evidence-linked failure memory from immutable S7 results.
        # Never mutate any prior cycle evidence or permit automatic execution.
        context['experiment_learning'] = build_experiment_learning(
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
            # Cycle-side summary cannot see gateway S7 trial records and
            # defaults to zero even when the immutable paired experiments
            # have already been evaluated. Reconcile only hash-verified S7
            # reports here; absence remains zero, never a fictitious pass.
            if isinstance(current['final_report'], dict):
                tested = 0
                for observed in current['history']:
                    generation = observed['generation']
                    stored = self._stored_experiment(db, sid, generation)
                    if stored is None:
                        continue
                    trials = stored['report'].get('experiments')
                    if (
                        stored.get('session_id') != sid
                        or stored.get('generation') != generation
                        or stored.get('original_generation_evidence_hash')
                        != observed['evidence_hash']
                        or not isinstance(trials, list)
                        or sorted(t['hypothesis_id'] for t in trials)
                        != sorted(observed['hypothesis_ids'])
                    ):
                        raise CycleStateError('gateway S7 summary evidence mismatch')
                    tested += len(trials)
                report = dict(current['final_report'])
                report['tested_hypotheses'] = tested
                report['gateway_s7_count_source'] = (
                    'HASH_VERIFIED_IMMUTABLE_GATEWAY_REPORTS'
                )
                report['all_proposed_hypotheses_measured'] = (
                    tested == report['proposed_hypotheses']
                )
                # S7 completeness says nothing about LLM authenticity,
                # external PIT, statistical independence or profitability.
                result['final_report'] = report
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
                # UX advice is added after verifying the sealed diagnostic hash;
                # legacy stages and the model's signed observation context stay identical.
                result['model_context'] = {
                    **context, 'experiment_quality_guidance': academic_diagnostic_quality_hint(),
                }
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
            if self._is_recent_replay(
                db, row, current, 'plan', token, args['plan'],
            ):
                return self.get({'session_id': sid})
            if row['phase'] != 'AWAITING_PLAN' or current['status'] != 'AWAITING_PROVIDER':
                raise CycleStateError('plan cannot be submitted in current state')
            if row['token'] != token:
                raise CycleStateError('invalid checkpoint token')
            plan = AlgorithmPlan.model_validate(args['plan'])
            compiled = compile_algorithm_plan(catalog, plan, data)
            # The canonical cycle rejects duplicate semantics and duplicate
            # effective entry/regime vectors. Apply those SAME checks here
            # before consuming the plan token or running model diagnosis.
            # A duplicate is a recoverable proposal error, not a reason to
            # interrupt every subsequent research generation.
            semantic_hash = content_hash(plan.model_dump(
                mode='json', exclude={'plan_id'},
            ))
            vectors = compiled.compiled.feature_values
            effective_hash = content_hash({
                'dataset_hash': data.dataset_hash,
                'entry': vectors['plan_entry'],
                'regime': vectors['plan_regime'],
            })
            for previous in current['history']:
                if previous['algorithm_semantic_hash'] == semantic_hash:
                    raise DuplicateAlgorithmPlanError(
                        'DUPLICATE_SEMANTIC_PLAN', previous['generation'],
                    )
                if previous['effective_signal_hash'] == effective_hash:
                    raise DuplicateAlgorithmPlanError(
                        'DUPLICATE_EFFECTIVE_SIGNALS', previous['generation'],
                    )
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
            self._record_submission(
                db, sid, 'plan', token, args['plan'], new_token,
                'AWAITING_DIAGNOSIS', current['completed_generations'],
            )
            db.execute(
                "INSERT OR IGNORE INTO generation_timings "
                "(session_id,generation,start_utc) VALUES(?,?,?)",
                (sid, current['completed_generations'] + 1,
                 datetime.now(timezone.utc).isoformat()),
            )
        return self.get({'session_id': sid})

    def submit_diagnosis(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(args, {'session_id','checkpoint_token','diagnosis',
                         'require_signal_change'},
                  {'session_id','checkpoint_token','diagnosis'})
        strict_signal = args.get('require_signal_change', False)
        if type(strict_signal) is not bool:
            raise ValueError('require_signal_change must be a boolean')
        sid, token, diagnosis = args['session_id'], args['checkpoint_token'], args['diagnosis']
        if not isinstance(diagnosis, dict):
            raise ValueError('diagnosis must be a structured object')
        # A lost MCP reply is recoverable without rerunning a generation.
        replay_request = {'diagnosis': diagnosis, 'require_signal_change': strict_signal}
        with self._connect() as db:
            row, _, _, current = self._state(db, sid)
            if self._is_recent_replay(
                db, row, current, 'diagnosis', token, replay_request,
            ):
                return self._evaluated_reply(sid, current['completed_generations'])
        # Recompute all observed evidence before any generation can be committed.
        pending = self.get({'session_id': sid})
        if (pending['checkpoint_phase'] != 'AWAITING_DIAGNOSIS'
                or pending['checkpoint_token'] != token):
            raise CycleStateError('invalid diagnosis checkpoint token or state')
        if diagnosis.get('context_hash') != pending['model_context']['context_hash']:
            raise CycleStateError('invalid diagnosis context hash')
        # S7 is automatically evaluated after the generation is committed.
        # Reject unsupported response metrics while the checkpoint is still
        # unclaimed, so the model can correct its diagnosis without creating
        # a committed generation lacking an experiment report.
        typed_diagnosis = DiagnosticResponse.model_validate(diagnosis)
        for hypothesis in typed_diagnosis.hypotheses:
            if hypothesis.expected_metric not in SUPPORTED_CONTROLLED_METRICS:
                raise ValueError(f'unsupported S7 metric: {hypothesis.expected_metric}')
        if strict_signal:
            # The plan is recomputed from its pinned catalog before evaluating
            # the structural proof; this rejects only a certain no-op, not a
            # data-mined candidate whose performance happens to be unchanged.
            with self._connect() as db:
                row, catalog, data, _ = self._state(db, sid)
                parent_plan = AlgorithmPlan.model_validate(json.loads(row['plan_json']))
                parent = compile_algorithm_plan(catalog, parent_plan, data).compiled.strategy
            uninformative = static_noop_hypotheses(parent, typed_diagnosis)
            if uninformative:
                raise ValueError(
                    'known static no-op experiment: ' + ', '.join(uninformative)
                    + '; edit diagnosis and resubmit using the same checkpoint token'
                )
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
            new_token = uuid4().hex
            next_phase = 'COMPLETED' if completed['status'] == 'COMPLETED' else 'AWAITING_PLAN'
            committed = db.execute('''UPDATE stages SET phase=?,token=?,plan_json=NULL,
            plan_digest=NULL,context_digest=NULL WHERE session_id=? AND phase='RUNNING' ''',
            (next_phase, new_token, sid))
            if committed.rowcount != 1:
                raise CycleStateError('diagnosis checkpoint finalization conflict')
            self._record_submission(
                db, sid, 'diagnosis', token, replay_request, new_token,
                next_phase, completed['completed_generations'],
            )
        # MCP-first shortcut: a complete research generation must carry its
        # measured experiment evidence into the NEXT LLM planning prompt.
        # Previously ChatGPT had to make an extra evaluate_* call and could
        # accidentally start the next generation from unmeasured hypotheses.
        # All comparison results use the existing immutable, idempotent S7
        # storage and the *same* development dataset as the original plan.
        return self._evaluated_reply(sid, completed['completed_generations'])

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
        """Operator-only crash reconciliation; caller has confirmed worker stopped.

        A completed underlying generation must have its measured S7 report
        recovered before exposing the next GPT planning checkpoint. Repeating
        a successful reconciliation is read-only and preserves token/evidence.
        """
        self._one(args, {'session_id'}, {'session_id'})
        sid = args['session_id']
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            if row['phase'] != 'RUNNING':
                if self._is_recovery_replay(db, row, current, 'reconcile'):
                    return self._recovery_reply(sid, current['completed_generations'])
                raise CycleStateError('reconcile only stalled running gateway checkpoint')
            # Check the previously recorded receipt too, fail closed on damage.
            self._is_recovery_replay(db, row, current, 'reconcile')
            cycle_status = current['status']
            if cycle_status == 'EXECUTING':
                # Existing cycle-side CAS token prevents a killed former worker
                # from committing evidence if it returns after reconciliation.
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

            # The cycle DB may have committed its immutable generation before
            # the gateway process died. Persist/re-check S7 before granting
            # access to next model prompts: corrupted proof must block recovery.
            generation = current['completed_generations']
            if generation > 0:
                self.evaluate_experiments({
                    'session_id': sid, 'generation': generation,
                })
            new_token = uuid4().hex
            changed = db.execute(
                'UPDATE stages SET phase=?,token=?,plan_json=NULL,'
                'plan_digest=NULL,context_digest=NULL '
                "WHERE session_id=? AND phase='RUNNING' AND token=?",
                (phase, new_token, sid, row['token']),
            )
            if changed.rowcount != 1:
                raise CycleStateError('concurrent gateway checkpoint change')
            self._store_recovery_receipt(
                db, sid, 'reconcile', phase, new_token, generation,
            )
        return self._recovery_reply(sid, generation)

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
            # A generation is finished only after S7 is durably verified.
            # Replays and old sessions without a recorded start never fabricate timing.
            db.execute(
                "UPDATE generation_timings SET end_utc=?, evidence_hash=? "
                "WHERE session_id=? AND generation=? AND end_utc IS NULL",
                (datetime.now(timezone.utc).isoformat(), original['evidence_hash'],
                 sid, generation),
            )
            return verified

    def resume(self, args: dict[str, Any]) -> dict[str, Any]:
        """Explicitly resume interrupted research; duplicate resume is a read."""
        self._one(args, {'session_id'}, {'session_id'})
        sid = args['session_id']
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            if row['phase'] != 'INTERRUPTED':
                if self._is_recovery_replay(db, row, current, 'resume'):
                    return self.get({'session_id': sid})
                raise CycleStateError('only interrupted academic MCP sessions can resume')
            self._is_recovery_replay(db, row, current, 'resume')
            if current['status'] not in ('INTERRUPTED', 'AWAITING_PROVIDER'):
                raise CycleStateError('only interrupted academic MCP sessions can resume')
            if current['status'] == 'INTERRUPTED':
                self.cycle.resume(sid, catalog, data)
            new_token = uuid4().hex
            changed = db.execute(
                "UPDATE stages SET phase='AWAITING_PLAN',token=?,plan_json=NULL,"
                "plan_digest=NULL,context_digest=NULL "
                "WHERE session_id=? AND phase='INTERRUPTED' AND token=?",
                (new_token, sid, row['token']),
            )
            if changed.rowcount != 1:
                raise CycleStateError('concurrent resume checkpoint change')
            self._store_recovery_receipt(
                db, sid, 'resume', 'AWAITING_PLAN', new_token,
                current['completed_generations'],
            )
        return self.get({'session_id': sid})
