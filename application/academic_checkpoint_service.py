"""Existing authenticated MCP resource: explicit GPT Plan→Audit→Diagnosis checkpoints.

The connected ChatGPT model is the Research Director. This service makes no
LLM HTTP calls and NEVER creates/rotates an MCP URL, OAuth record or key.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.data.contracts import MarketDataSet
from core.data.parquet import ParquetDataProvider
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from orchestration.evaluation_runner import resolve_project_input
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlan,
    audit_algorithm_plan,
    build_algorithm_plan_context,
    compile_algorithm_plan,
    evaluate_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog
from research.indicator_engine.controlled_experiments import (
    SUPPORTED_CONTROLLED_METRICS,
    compare_controlled_experiments,
)
from research.indicator_engine.development_benchmark import compare_qqq_development_benchmarks
from research.indicator_engine.experiment_preflight import (
    academic_diagnostic_quality_hint,
    static_noop_hypotheses,
)
from research.indicator_engine.external_reference import (
    audit_s6_external_reference,
    capture_s6_external_reference,
    get_s6_external_reference,
)
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.inherited_experiments import compare_inherited_experiments
from research.indicator_engine.s6_seed import S6_SIGNALS, seed_s6_references
from research.indicator_engine.seed import seed_approved_references
from research.indicator_engine.signals import verify_signal_on_synthetic_prices
from research.indicator_engine.strategy_adapter import CompiledAcademicStrategy
from research.llm.adaptive_direction import build_research_direction
from research.llm.autonomous_cycle import AcademicCycleService, CycleStateError
from research.llm.diagnostic_research import DiagnosticResponse, build_diagnostic_context
from research.llm.director import ResearchIntent
from research.llm.economic_feedback import build_economic_feedback, gate_research_direction
from research.llm.execution_policy import research_execution_policy
from research.llm.experiment_learning import build_experiment_learning
from research.llm.intent_bridge import apply_intent
from research.llm.lineage_replay import verified_child_successor
from research.llm.lineage_selection import (
    IneligibleCountedChild,
    choose_development_parent,
    compile_replayed_successor,
    replay_counted_s7_child,
    replay_lineage_candidate,
)
from strategy_ir.schema import StrategyIR


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


class _SubmittedDiagnosisOnly:
    """An inherited plan is already pinned and audited; GPT authors only S2."""

    def __init__(self, diagnosis: dict[str, Any]):
        self.diagnosis = diagnosis

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        if context.get("schema") != "research-diagnostic-context-v1" or self.diagnosis.get(
            "context_hash"
        ) != context.get("context_hash"):
            raise CycleStateError("inherited S2 diagnosis context mismatch")
        return deepcopy(self.diagnosis)


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
        # Supplemental timing; original canonical evidence remains unchanged.
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
        # Sidecar proof never edits immutable generation evidence.
        db.execute('''CREATE TABLE IF NOT EXISTS successor_lineages (
            session_id TEXT NOT NULL, origin_generation INTEGER NOT NULL,
            request_hash TEXT NOT NULL, result_json TEXT NOT NULL,
            result_hash TEXT NOT NULL,
            PRIMARY KEY(session_id, origin_generation, request_hash)
        )''')
        # Immutable per-next-generation parent *selection*, not promotion.
        db.execute('''CREATE TABLE IF NOT EXISTS parent_selections (
            session_id TEXT NOT NULL, next_generation INTEGER NOT NULL,
            lineage_report_hash TEXT NOT NULL, selection_hash TEXT NOT NULL,
            selection_json TEXT NOT NULL,
            PRIMARY KEY(session_id, next_generation)
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

    def _selected_development_parent(
        self,
        catalog: ResearchCatalog,
        data: MarketDataSet,
        status: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Pin a full-fill-replayed S7 successor for the next generation.

        A pinned selection has NO permission to replace AlgorithmPlan: the
        counted S2/S7 adapter is still separately required. Never write to
        original cycle generations or increment the research counter here.
        """
        # Parent selection is currently scoped to the one-symbol QQQ
        # costed comparator. Never prevent non-QQQ legacy sessions from
        # planning because a benchmark is not applicable.
        if not data.bars or any(bar.symbol != "QQQ" for bar in data.bars):
            return None
        sid = status["session_id"]
        next_generation = status["completed_generations"] + 1
        with self._connect() as db:
            pinned = db.execute(
                "SELECT * FROM parent_selections WHERE session_id=? AND next_generation=?",
                (sid, next_generation),
            ).fetchone()
            if pinned is not None:
                selection: dict[str, Any] = json.loads(pinned["selection_json"])
                body = {k: v for k, v in selection.items() if k != "selection_hash"}
                if (
                    pinned["selection_hash"] != content_hash(body)
                    or selection.get("selection_hash") != pinned["selection_hash"]
                    or pinned["lineage_report_hash"] != selection.get("lineage_report_hash")
                ):
                    raise CycleStateError("parent selection integrity failure")
                source = selection["source_generation"]
                if (
                    type(source) is not int
                    or source < 1
                    or source > status["completed_generations"]
                    or status["history"][source - 1]["evidence_hash"]
                    != selection["source_evidence_hash"]
                ):
                    raise CycleStateError("parent selection origin mismatch")
                if selection.get("source_kind") == "COUNTED_S7_CHILD":
                    stored = self._stored_experiment(db, sid, source)
                    if stored is None or stored["record_hash"] != selection["source_report_hash"]:
                        raise CycleStateError("counted S7 selected proof disappeared")
                    source_row = status["history"][source - 1]
                    expected_lineage = content_hash(
                        {
                            "schema": "counted-s7-child-origin-v1",
                            "source_generation": source,
                            "source_evidence_hash": source_row["evidence_hash"],
                            "source_report_hash": stored["record_hash"],
                            "hypothesis_id": selection["hypothesis_id"],
                            "child_strategy_hash": selection["successor_strategy_hash"],
                        }
                    )
                    if expected_lineage != selection["lineage_report_hash"]:
                        raise CycleStateError("counted S7 selected origin mismatch")
                else:
                    proof = db.execute(
                        "SELECT result_hash FROM successor_lineages "
                        "WHERE session_id=? AND origin_generation=? "
                        "AND result_hash=?",
                        (sid, source, selection["lineage_report_hash"]),
                    ).fetchone()
                    if proof is None:
                        raise CycleStateError("parent selection proof disappeared")
                return selection
            rows = db.execute(
                "SELECT origin_generation,result_json,result_hash "
                "FROM successor_lineages WHERE session_id=? "
                "ORDER BY origin_generation,request_hash",
                (sid,),
            ).fetchall()
            candidates = []
            for row in rows:
                proof = json.loads(row["result_json"])
                # Older sidecars and legacy test fixtures remain readable.
                if proof.get("schema") != "p0-3-child-to-successor-development-v1":
                    continue
                source = row["origin_generation"]
                if (
                    type(source) is not int
                    or not 1 <= source <= status["completed_generations"]
                    or proof.get("source_generation") != source
                    or proof.get("source_evidence_hash")
                    != status["history"][source - 1]["evidence_hash"]
                    or proof.get("report_hash") != row["result_hash"]
                    or content_hash({k: v for k, v in proof.items() if k != "report_hash"})
                    != row["result_hash"]
                ):
                    raise CycleStateError("parent candidate evidence integrity failure")
                measured = self._stored_experiment(db, sid, source)
                if measured is None:
                    raise CycleStateError("parent candidate is missing S7 evidence")
                candidate = replay_lineage_candidate(
                    catalog,
                    data,
                    status["history"][source - 1],
                    measured,
                    proof,
                )
                if (
                    candidate["source_evidence_hash"] != proof["source_evidence_hash"]
                    or candidate["lineage_report_hash"] != row["result_hash"]
                    or candidate["successor_strategy_hash"] != proof["successor_strategy_hash"]
                ):
                    raise CycleStateError("parent replay candidate identity mismatch")
                candidates.append(candidate)
            baseline = choose_development_parent(candidates)
            counted_tested = 0
            rejected: list[dict[str, Any]] = []
            valid_counted = 0
            comparisons: list[dict[str, Any]] = []
            for original in status["history"]:
                if original.get("inherited_strategy_ir") is None:
                    continue
                generation = original["generation"]
                report = self._stored_experiment(db, sid, generation)
                if report is None:
                    # The sealed S7 result must be present before next planning.
                    raise CycleStateError("counted generation missing S7 measurement")
                parent = self._inherited_from_evidence(catalog, data, original)
                for experiment in original["experiments"]:
                    counted_tested += 1
                    hypothesis_id = experiment["hypothesis_id"]
                    try:
                        candidate, _ = replay_counted_s7_child(
                            catalog,
                            data,
                            original,
                            report,
                            parent,
                            hypothesis_id,
                        )
                    except IneligibleCountedChild:
                        rejected.append(
                            {
                                "source_generation": generation,
                                "hypothesis_id": hypothesis_id,
                                "reason": "S7_NO_CHANGED_FILLS_OR_DEGENERATE",
                            }
                        )
                        continue
                    candidates.append(candidate)
                    qualified = choose_development_parent([candidate]) is not None
                    if qualified:
                        valid_counted += 1
                    champion_metrics = baseline["parent_quality"] if baseline is not None else None
                    comparisons.append(
                        {
                            "source_generation": generation,
                            "hypothesis_id": hypothesis_id,
                            "child_strategy_hash": candidate["successor_strategy_hash"],
                            "parent_s7_report_hash": candidate["source_report_hash"],
                            "replay_verified": True,
                            "policy_eligible": qualified,
                            "total_return": candidate["successor_total_return"],
                            "max_drawdown": candidate["successor_max_drawdown"],
                            "closed_trades": candidate["successor_closed_trades"],
                            "market_exposure": candidate["successor_market_exposure"],
                            "qqq_buy_and_hold_return": candidate["qqq_buy_and_hold_return"],
                            "qqq_exposure_matched_return": candidate["qqq_exposure_matched_return"],
                            "vs_champion_return_pp": (
                                100
                                * (
                                    candidate["successor_total_return"]
                                    - champion_metrics["total_return"]
                                )
                                if champion_metrics is not None
                                else None
                            ),
                            "vs_champion_mdd_pp": (
                                100
                                * (
                                    candidate["successor_max_drawdown"]
                                    - champion_metrics["max_drawdown"]
                                )
                                if champion_metrics is not None
                                else None
                            ),
                        }
                    )
            chosen = choose_development_parent(candidates)
            if chosen is None:
                return None
            for entry in comparisons:
                if not entry["policy_eligible"]:
                    entry["decision"] = "REJECTED_ECONOMIC_OR_RISK_GATES"
                elif chosen.get("source_kind") == "COUNTED_S7_CHILD" and (
                    chosen["source_generation"] == entry["source_generation"]
                    and chosen["hypothesis_id"] == entry["hypothesis_id"]
                ):
                    entry["decision"] = "PROMOTED_BEST_VERIFIED_CANDIDATE"
                else:
                    entry["decision"] = "RETAINED_HIGHER_RANKED_PARENT"
            body = {k: v for k, v in chosen.items() if k != "selection_hash"}
            body["candidate_review"] = {
                "counted_s7_tested": counted_tested,
                "eligible_counted_s7": valid_counted,
                "rejected_counted_s7": len(rejected),
                "rejections": rejected,
                "comparisons": comparisons,
                "champion_retained": baseline is not None
                and (baseline["successor_strategy_hash"] == chosen["successor_strategy_hash"]),
                "baseline_parent_strategy_hash": (
                    baseline["successor_strategy_hash"] if baseline is not None else None
                ),
            }
            chosen = {**body, "selection_hash": content_hash(body)}
            # The old stage may still be read repeatedly. Pin *once* so
            # later additional sidecars cannot silently replace the parent.
            db.execute(
                "INSERT OR IGNORE INTO parent_selections "
                "(session_id,next_generation,lineage_report_hash,selection_hash,selection_json) "
                "VALUES(?,?,?,?,?)",
                (
                    sid,
                    next_generation,
                    chosen["lineage_report_hash"],
                    chosen["selection_hash"],
                    json.dumps(chosen, sort_keys=True),
                ),
            )
        return self._selected_development_parent(catalog, data, status)

    def _selected_ir(
        self,
        catalog: ResearchCatalog,
        data: MarketDataSet,
        state: dict[str, Any],
    ) -> tuple[CompiledAcademicStrategy, dict[str, Any], dict[str, Any]]:
        """Verify P0-3A S7 provenance and reproduce the pinned next parent."""
        selected = self._selected_development_parent(catalog, data, state)
        if selected is None:
            raise CycleStateError("no verified successor selected for inheritance")
        source = selected["source_generation"]
        original = state["history"][source - 1]
        with self._connect() as db:
            measured = self._stored_experiment(db, state["session_id"], source)
            if selected.get("source_kind") == "COUNTED_S7_CHILD":
                saved = None
            else:
                saved = db.execute(
                    "SELECT result_json,result_hash FROM successor_lineages "
                    "WHERE session_id=? AND origin_generation=? AND result_hash=?",
                    (state["session_id"], source, selected["lineage_report_hash"]),
                ).fetchone()
        if measured is None:
            raise CycleStateError("selected inheritance source missing")
        if selected.get("source_kind") == "COUNTED_S7_CHILD":
            if measured["record_hash"] != selected["source_report_hash"]:
                raise CycleStateError("selected S7 report changed")
            parent_original = self._inherited_from_evidence(catalog, data, original)
            evidence, parent = replay_counted_s7_child(
                catalog,
                data,
                original,
                measured,
                parent_original,
                selected["hypothesis_id"],
            )
            if any(
                evidence.get(key) != selected.get(key)
                for key in (
                    "source_evidence_hash",
                    "source_report_hash",
                    "lineage_report_hash",
                    "successor_strategy_hash",
                    "strategy_equity_hash",
                )
            ):
                raise CycleStateError("selected S7 StrategyIR or cost identity mismatch")
        else:
            if saved is None:
                raise CycleStateError("selected lineage record missing")
            proof = json.loads(saved["result_json"])
            if saved["result_hash"] != proof.get("report_hash"):
                raise CycleStateError("selected inheritance report hash mismatch")
            parent = compile_replayed_successor(catalog, data, original, measured, proof)
        if parent.strategy_hash != selected["successor_strategy_hash"]:
            raise CycleStateError("selected counted parent StrategyIR mismatch")
        return parent, original, selected

    def _materialize_inherited(
        self,
        catalog: ResearchCatalog,
        data: MarketDataSet,
        state: dict[str, Any],
        pending: dict[str, Any],
    ) -> tuple[CompiledAcademicStrategy, CompiledAcademicStrategy, dict[str, Any]]:
        if pending.get("schema") != "p0-3b-inherited-pending-v1":
            raise CycleStateError("unknown inherited pending schema")
        parent, source, selection = self._selected_ir(catalog, data, state)
        source_plan = (
            source["base_algorithm_plan"]
            if source.get("inherited_strategy_ir") is not None
            else source["algorithm_plan"]
        )
        if (
            pending.get("parent_selection_hash") != selection["selection_hash"]
            or pending.get("base_algorithm_plan") != source_plan
        ):
            raise CycleStateError("pending inherited parent selection mismatch")
        intent = ResearchIntent.model_validate(pending["inherited_intent"])
        if (
            intent.mode != "structure"
            or intent.parent_ids != (parent.strategy.strategy_id,)
            or intent.feature_proposal is not None
            or intent.primitive_request is not None
            or not 1 <= len(intent.operations) <= 6
        ):
            raise CycleStateError("invalid inherited mutation intent")
        child = apply_intent(parent.strategy, intent, research_feature_specs())
        digest = content_hash(child.model_dump(mode="json", by_alias=True))
        if digest != pending.get("strategy_hash"):
            raise CycleStateError("inherited child StrategyIR changed after staging")
        proof = {
            "schema": "p0-3b-counted-inheritance-input-v1",
            "source_generation": selection["source_generation"],
            "source_evidence_hash": selection["source_evidence_hash"],
            "parent_strategy_hash": parent.strategy_hash,
            "origin_lineage_hash": selection["lineage_report_hash"],
            "parent_selection_hash": selection["selection_hash"],
        }
        return parent, replace(parent, strategy=child, strategy_hash=digest), proof

    def _inherited_from_evidence(
        self,
        catalog: ResearchCatalog,
        data: MarketDataSet,
        original: dict[str, Any],
    ) -> CompiledAcademicStrategy:
        base = compile_algorithm_plan(
            catalog,
            AlgorithmPlan.model_validate(original["base_algorithm_plan"]),
            data,
        )
        inherited = StrategyIR.model_validate(original["inherited_strategy_ir"])
        digest = content_hash(inherited.model_dump(mode="json", by_alias=True))
        if (
            digest != original["strategy_hash"]
            or base.compiled.dataset_hash != original["dataset_hash"]
        ):
            raise CycleStateError("saved counted inherited StrategyIR integrity mismatch")
        compiled = replace(base.compiled, strategy=inherited, strategy_hash=digest)
        audited = audit_inherited_decisions(compiled, data)
        if (
            audited.trace_hash != original["audit_hash"]
            or abs(audited.evaluation.final_equity - original["measured_final_equity"]) > 1e-6
        ):
            raise CycleStateError("saved inherited S2 evidence cannot replay")
        return compiled

    def _context(
        self,
        catalog: ResearchCatalog,
        data: MarketDataSet,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        context = build_algorithm_plan_context(catalog, data)
        context["generation"] = status["completed_generations"] + 1
        # Verified QQQ costed B&H and historical, non-tradable risk proxies.
        # Replay the latest audited strategy; never trust LLM-claimed metrics.
        last = status["history"][-1] if status["history"] else None
        equity = None
        exposure = None
        if last is not None:
            if last.get("inherited_strategy_ir") is not None:
                previous_compiled = self._inherited_from_evidence(catalog, data, last)
                evaluation = audit_inherited_decisions(previous_compiled, data).evaluation
            else:
                plan = AlgorithmPlan.model_validate(last["algorithm_plan"])
                compiled = compile_algorithm_plan(catalog, plan, data)
                if (
                    compiled.plan_hash != last["plan_hash"]
                    or compiled.compiled.strategy_hash != last["strategy_hash"]
                    or last["dataset_hash"] != data.dataset_hash
                ):
                    raise CycleStateError("previous generation benchmark identity mismatch")
                evaluation = evaluate_algorithm_plan(catalog, compiled, data)
            if abs(evaluation.final_equity - last["measured_final_equity"]) > 1e-7:
                raise CycleStateError("previous generation equity replay mismatch")
            equity = evaluation.equity_curve
            exposure = last["metrics"]["exposure"]
        if data.bars and all(bar.symbol == "QQQ" for bar in data.bars):
            context["benchmark_comparison"] = compare_qqq_development_benchmarks(
                data,
                strategy_equity_curve=equity,
                realized_exposure=exposure,
            )
        else:
            # Prevent a QQQ comparator from blocking other research symbols.
            context["benchmark_comparison"] = {
                "status": "NOT_APPLICABLE_NON_QQQ",
                "independent_oos_approved": False,
                "broker_executable": False,
            }
        if last is not None:
            context["benchmark_comparison"].update(
                {
                    "strategy_generation": last["generation"],
                    "strategy_total_return": last["metrics"]["total_return"],
                    "strategy_max_drawdown": last["metrics"]["max_drawdown"],
                    "strategy_evidence_hash": last["evidence_hash"],
                }
            )
        # Validate stored experiment checksum before it influences future LLM
        # direction. S7-v1 reports lack execution attribution and remain
        # readable, but cannot support the newer direction allocator.
        scored_reports: dict[int, dict[str, Any]] = {}
        with self._connect() as db:
            for item in status["history"]:
                observed = self._stored_experiment(db, status["session_id"], item["generation"])
                if observed is not None and all(
                    "execution_delta" in experiment
                    for experiment in observed["report"].get("experiments", [])
                ):
                    scored_reports[item["generation"]] = observed
        # Economic feedback is derived from already hash-verified immutable
        # paired comparisons. A trade-count direction match is NOT sufficient
        # evidence for EVOLVE if the same child lost development money.
        # These are advisory review candidates, never auto-executed strategies.
        context["economic_feedback"] = build_economic_feedback(
            status["history"],
            scored_reports,
        )
        # Only lineage reports with intact hashes and immutable source ancestry
        # may influence the next GPT request. No automatic generation promotion.
        successors = []
        with self._connect() as db:
            saved = db.execute(
                "SELECT origin_generation,result_json,result_hash "
                "FROM successor_lineages WHERE session_id=? "
                "ORDER BY rowid DESC LIMIT 12",
                (status["session_id"],),
            ).fetchall()
        for record in saved:
            lineage: dict[str, Any] = json.loads(record["result_json"])
            expected_hash = content_hash(
                {key: value for key, value in lineage.items() if key != "report_hash"}
            )
            source_index = record["origin_generation"] - 1
            if (
                lineage.get("report_hash") != record["result_hash"]
                or expected_hash != record["result_hash"]
                or not 0 <= source_index < len(status["history"])
                or lineage.get("source_evidence_hash")
                != status["history"][source_index]["evidence_hash"]
            ):
                raise CycleStateError("successor lineage origin or checksum mismatch")
            successors.append(
                {
                    "source_generation": lineage["source_generation"],
                    "hypothesis_id": lineage["hypothesis_id"],
                    "source_evidence_hash": lineage["source_evidence_hash"],
                    "child_strategy_hash": lineage["reproduced_child_strategy_hash"],
                    "successor_strategy_hash": lineage["successor_strategy_hash"],
                    "successor_final_equity": lineage["successor_final_equity"],
                    "successor_total_return": lineage["successor_total_return"],
                    "successor_max_drawdown": lineage["successor_max_drawdown"],
                    "improvement_vs_child_pp": lineage["improvement_vs_child_pp"],
                    "continuation_intent": lineage["continuation_intent"],
                    "lineage_report_hash": lineage["report_hash"],
                    "independent_oos_approved": False,
                    "generation_counter_incremented": False,
                }
            )
        context["verified_successor_lineages"] = successors
        context["selected_development_parent"] = self._selected_development_parent(
            catalog,
            data,
            status,
        )
        selected = context["selected_development_parent"]
        context["inheritance_decision"] = (
            selected.get("candidate_review", {})
            if selected is not None
            else {"status": "NO_VERIFIED_PARENT"}
        )
        if selected is not None:
            parent, _, _ = self._selected_ir(catalog, data, status)
            context["output_contract"] = "InheritedResearchIntent"
            context["inherited_research_intent_schema"] = ResearchIntent.model_json_schema()
            context["inherited_parent_strategy_id"] = parent.strategy.strategy_id
            context["inherited_parent_strategy_hash"] = parent.strategy_hash
            context["inherited_parent_entry_conditions"] = [
                c.model_dump(mode="json") for c in parent.strategy.entry.conditions
            ]
            context["inherited_parent_exit_conditions"] = [
                c.model_dump(mode="json") for c in parent.strategy.exit.conditions
            ]
        context["counted_parent_inheritance_ready"] = selected is not None
        context["counted_parent_inheritance_gate"] = (
            "DEVELOPMENT_ONLY_S2_S7_COUNTED_MUTATION_NO_ORDERS"
            if selected is not None
            else "NO_VERIFIED_PARENT_FALLBACK_ALGORITHM_PLAN"
        )
        context["research_direction"] = gate_research_direction(
            build_research_direction(status["history"], scored_reports),
            context["economic_feedback"],
        )
        # Regenerate evidence-linked failure memory from immutable S7 results.
        # Never mutate any prior cycle evidence or permit automatic execution.
        context["experiment_learning"] = build_experiment_learning(
            status["history"],
            scored_reports,
        )
        if status["history"]:
            previous = status["history"][-1]
            context["prior_research"] = {
                "generation": previous["generation"],
                "evidence_hash": previous["evidence_hash"],
                "audit_hash": previous["audit_hash"],
                "diagnostic_proposal_hash": previous["diagnostic_proposal_hash"],
                "causal_status": previous["causal_status"],
                "analysis_summary": previous["analysis_summary"],
                "experiments": previous["experiments"],
                "metrics": previous["metrics"],
                "prior_algorithm_semantic_hash": previous["algorithm_semantic_hash"],
            }
            with self._connect() as db:
                measured = self._stored_experiment(
                    db,
                    status["session_id"],
                    previous["generation"],
                )
            if measured is not None:
                context["prior_research"]["controlled_experiments"] = measured
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
        self._one(args, {"session_id"}, {"session_id"})
        sid = args["session_id"]
        if not isinstance(sid, str) or len(sid) != 32:
            raise ValueError("session_id must be 32 hex characters")
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            result: dict[str, Any] = {
                **current,
                "checkpoint_phase": row["phase"],
                "catalog_version": row["catalog_version"],
                "llm_controller": "authenticated_chatgpt_mcp_client",
                "research_execution_policy": research_execution_policy(),
                "mcp_url_unchanged": True,
            }
            # Cycle-side summary cannot see gateway S7 trial records and
            # defaults to zero even when the immutable paired experiments
            # have already been evaluated. Reconcile only hash-verified S7
            # reports here; absence remains zero, never a fictitious pass.
            if isinstance(current["final_report"], dict):
                tested = 0
                for observed in current["history"]:
                    generation = observed["generation"]
                    stored = self._stored_experiment(db, sid, generation)
                    if stored is None:
                        continue
                    trials = stored["report"].get("experiments")
                    if (
                        stored.get("session_id") != sid
                        or stored.get("generation") != generation
                        or stored.get("original_generation_evidence_hash")
                        != observed["evidence_hash"]
                        or not isinstance(trials, list)
                        or sorted(t["hypothesis_id"] for t in trials)
                        != sorted(observed["hypothesis_ids"])
                    ):
                        raise CycleStateError("gateway S7 summary evidence mismatch")
                    tested += len(trials)
                report = dict(current["final_report"])
                report["tested_hypotheses"] = tested
                report["gateway_s7_count_source"] = "HASH_VERIFIED_IMMUTABLE_GATEWAY_REPORTS"
                report["all_proposed_hypotheses_measured"] = tested == report["proposed_hypotheses"]
                # S7 completeness says nothing about LLM authenticity,
                # external PIT, statistical independence or profitability.
                result["final_report"] = report
            if row["phase"] == "AWAITING_PLAN":
                if current["status"] != "AWAITING_PROVIDER":
                    raise CycleStateError("checkpoint phase mismatch")
                result["checkpoint_token"] = row["token"]
                result["model_context"] = self._context(catalog, data, current)
                result["model_context"]["catalog_version"] = row["catalog_version"]
            elif row["phase"] == "AWAITING_DIAGNOSIS":
                if current["status"] != "AWAITING_PROVIDER":
                    raise CycleStateError("checkpoint phase mismatch")
                pending = json.loads(row["plan_json"])
                if pending.get("schema") == "p0-3b-inherited-pending-v1":
                    parent, inherited, _ = self._materialize_inherited(
                        catalog,
                        data,
                        current,
                        pending,
                    )
                    audit = audit_inherited_decisions(inherited, data)
                    strategy = inherited.strategy
                else:
                    plan = AlgorithmPlan.model_validate(pending)
                    compiled = compile_algorithm_plan(catalog, plan, data)
                    audit = audit_algorithm_plan(catalog, compiled, data)
                    strategy = compiled.compiled.strategy
                if content_hash(pending) != row["plan_digest"]:
                    raise CycleStateError("pending algorithm integrity mismatch")
                context = build_diagnostic_context(audit, strategy)
                if context["context_hash"] != row["context_digest"]:
                    raise CycleStateError("pending analysis integrity mismatch")
                result["checkpoint_token"] = row["token"]
                # UX advice is added after verifying the sealed diagnostic hash;
                # legacy stages and the model's signed observation context stay identical.
                result["model_context"] = {
                    **context,
                    "experiment_quality_guidance": academic_diagnostic_quality_hint(),
                }
                result["status"] = "AWAITING_DIAGNOSIS"
            elif row["phase"] not in ("COMPLETED", "INTERRUPTED", "RUNNING", "CANCELLED"):
                raise CycleStateError("invalid checkpoint state")
            return result

    def _stage_inherited_plan(
        self,
        db: sqlite3.Connection,
        row: sqlite3.Row,
        catalog: ResearchCatalog,
        data: MarketDataSet,
        state: dict[str, Any],
        args: dict[str, Any],
    ) -> None:
        parent, original, selected = self._selected_ir(catalog, data, state)
        intent = ResearchIntent.model_validate(args["plan"])
        if (
            intent.mode != "structure"
            or intent.parent_ids != (parent.strategy.strategy_id,)
            or intent.feature_proposal is not None
            or intent.primitive_request is not None
            or not 1 <= len(intent.operations) <= 6
        ):
            raise ValueError("inherited plan requires a registered, bounded ResearchIntent")
        child = apply_intent(parent.strategy, intent, research_feature_specs())
        digest = content_hash(child.model_dump(mode="json", by_alias=True))
        if digest == parent.strategy_hash or any(
            item["strategy_hash"] == digest for item in state["history"]
        ):
            raise ValueError("DUPLICATE_INHERITED_STRATEGY: change next mutation")
        compiled = replace(parent, strategy=child, strategy_hash=digest)
        audit = audit_inherited_decisions(compiled, data)
        context = build_diagnostic_context(audit, child)
        body = {
            "schema": "p0-3b-inherited-pending-v1",
            "base_algorithm_plan": (
                original["base_algorithm_plan"]
                if original.get("inherited_strategy_ir") is not None
                else original["algorithm_plan"]
            ),
            "parent_selection_hash": selected["selection_hash"],
            "inherited_intent": intent.model_dump(mode="json"),
            "strategy_hash": digest,
        }
        token = uuid4().hex
        updated = db.execute(
            "UPDATE stages SET phase='AWAITING_DIAGNOSIS',token=?,plan_json=?,"
            "plan_digest=?,context_digest=? WHERE session_id=? "
            "AND phase='AWAITING_PLAN' AND token=?",
            (
                token,
                json.dumps(body, sort_keys=True),
                content_hash(body),
                context["context_hash"],
                state["session_id"],
                row["token"],
            ),
        )
        if updated.rowcount != 1:
            raise CycleStateError("concurrent inherited plan checkpoint claim")
        self._record_submission(
            db,
            state["session_id"],
            "plan",
            row["token"],
            args["plan"],
            token,
            "AWAITING_DIAGNOSIS",
            state["completed_generations"],
        )
        db.execute(
            "INSERT OR IGNORE INTO generation_timings "
            "(session_id,generation,start_utc) VALUES(?,?,?)",
            (
                state["session_id"],
                state["completed_generations"] + 1,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def submit_plan(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(
            args,
            {"session_id", "checkpoint_token", "plan"},
            {"session_id", "checkpoint_token", "plan"},
        )
        sid, token = args["session_id"], args["checkpoint_token"]
        with self._connect() as db:
            row, catalog, data, current = self._state(db, sid)
            if self._is_recent_replay(
                db,
                row,
                current,
                "plan",
                token,
                args["plan"],
            ):
                return self.get({"session_id": sid})
            if row["phase"] != "AWAITING_PLAN" or current["status"] != "AWAITING_PROVIDER":
                raise CycleStateError("plan cannot be submitted in current state")
            if row["token"] != token:
                raise CycleStateError("invalid checkpoint token")
            if self._selected_development_parent(catalog, data, current) is not None:
                self._stage_inherited_plan(db, row, catalog, data, current, args)
                db.commit()
                return self.get({"session_id": sid})
            plan = AlgorithmPlan.model_validate(args["plan"])
            compiled = compile_algorithm_plan(catalog, plan, data)
            # The canonical cycle rejects duplicate semantics and duplicate
            # effective entry/regime vectors. Apply those SAME checks here
            # before consuming the plan token or running model diagnosis.
            # A duplicate is a recoverable proposal error, not a reason to
            # interrupt every subsequent research generation.
            semantic_hash = content_hash(
                plan.model_dump(
                    mode="json",
                    exclude={"plan_id"},
                )
            )
            vectors = compiled.compiled.feature_values
            effective_hash = content_hash(
                {
                    "dataset_hash": data.dataset_hash,
                    "entry": vectors["plan_entry"],
                    "regime": vectors["plan_regime"],
                }
            )
            for previous in current["history"]:
                if previous["algorithm_semantic_hash"] == semantic_hash:
                    raise ValueError(
                        "DUPLICATE_SEMANTIC_PLAN: previously tested generation "
                        f"{previous['generation']}; revise the plan and resubmit "
                        "using the same checkpoint token"
                    )
                if previous["effective_signal_hash"] == effective_hash:
                    raise ValueError(
                        "DUPLICATE_EFFECTIVE_SIGNALS: same historical entry/regime "
                        f"signals as generation {previous['generation']}; revise "
                        "the plan and resubmit using the same checkpoint token"
                    )
            audit = audit_algorithm_plan(catalog, compiled, data)
            context = build_diagnostic_context(audit, compiled.compiled.strategy)
            pending = plan.model_dump(mode="json")
            new_token = uuid4().hex
            result = db.execute(
                """UPDATE stages SET phase='AWAITING_DIAGNOSIS',token=?,plan_json=?,
                plan_digest=?,context_digest=? WHERE session_id=? AND phase='AWAITING_PLAN'
                AND token=?""",
                (
                    new_token,
                    json.dumps(pending, sort_keys=True),
                    content_hash(pending),
                    context["context_hash"],
                    sid,
                    token,
                ),
            )
            if result.rowcount != 1:
                raise CycleStateError("concurrent plan checkpoint was claimed")
            self._record_submission(
                db,
                sid,
                "plan",
                token,
                args["plan"],
                new_token,
                "AWAITING_DIAGNOSIS",
                current["completed_generations"],
            )
            db.execute(
                "INSERT OR IGNORE INTO generation_timings "
                "(session_id,generation,start_utc) VALUES(?,?,?)",
                (sid, current["completed_generations"] + 1, datetime.now(timezone.utc).isoformat()),
            )
        return self.get({"session_id": sid})

    def submit_diagnosis(self, args: dict[str, Any]) -> dict[str, Any]:
        self._one(
            args,
            {"session_id", "checkpoint_token", "diagnosis", "require_signal_change"},
            {"session_id", "checkpoint_token", "diagnosis"},
        )
        strict_signal = args.get("require_signal_change", False)
        if type(strict_signal) is not bool:
            raise ValueError("require_signal_change must be a boolean")
        sid, token, diagnosis = args["session_id"], args["checkpoint_token"], args["diagnosis"]
        if not isinstance(diagnosis, dict):
            raise ValueError("diagnosis must be a structured object")
        # A lost MCP reply is recoverable without rerunning a generation.
        replay_request = {"diagnosis": diagnosis, "require_signal_change": strict_signal}
        with self._connect() as db:
            row, _, _, current = self._state(db, sid)
            if self._is_recent_replay(
                db,
                row,
                current,
                "diagnosis",
                token,
                replay_request,
            ):
                return self._evaluated_reply(sid, current["completed_generations"])
        # Recompute all observed evidence before any generation can be committed.
        pending = self.get({"session_id": sid})
        if (
            pending["checkpoint_phase"] != "AWAITING_DIAGNOSIS"
            or pending["checkpoint_token"] != token
        ):
            raise CycleStateError("invalid diagnosis checkpoint token or state")
        if diagnosis.get("context_hash") != pending["model_context"]["context_hash"]:
            raise CycleStateError("invalid diagnosis context hash")
        # S7 is automatically evaluated after the generation is committed.
        # Reject unsupported response metrics while the checkpoint is still
        # unclaimed, so the model can correct its diagnosis without creating
        # a committed generation lacking an experiment report.
        typed_diagnosis = DiagnosticResponse.model_validate(diagnosis)
        for hypothesis in typed_diagnosis.hypotheses:
            if hypothesis.expected_metric not in SUPPORTED_CONTROLLED_METRICS:
                raise ValueError(f"unsupported S7 metric: {hypothesis.expected_metric}")
        if strict_signal:
            # The plan is recomputed from its pinned catalog before evaluating
            # the structural proof; this rejects only a certain no-op, not a
            # data-mined candidate whose performance happens to be unchanged.
            with self._connect() as db:
                row, catalog, data, _ = self._state(db, sid)
                staged = json.loads(row["plan_json"])
                if staged.get("schema") == "p0-3b-inherited-pending-v1":
                    source_state = self.cycle.get(sid, catalog, data)
                    _, inherited, _ = self._materialize_inherited(
                        catalog,
                        data,
                        source_state,
                        staged,
                    )
                    parent = inherited.strategy
                else:
                    parent_plan = AlgorithmPlan.model_validate(staged)
                    parent = compile_algorithm_plan(
                        catalog,
                        parent_plan,
                        data,
                    ).compiled.strategy
            uninformative = static_noop_hypotheses(parent, typed_diagnosis)
            if uninformative:
                raise ValueError(
                    "known static no-op experiment: "
                    + ", ".join(uninformative)
                    + "; edit diagnosis and resubmit using the same checkpoint token"
                )
        with self._connect() as db:
            row = db.execute("SELECT * FROM stages WHERE session_id=?", (sid,)).fetchone()
            assert row is not None
            updated = db.execute(
                "UPDATE stages SET phase='RUNNING' WHERE session_id=? "
                "AND phase='AWAITING_DIAGNOSIS' AND token=?",
                (sid, token),
            )
            if updated.rowcount != 1:
                raise CycleStateError("concurrent diagnosis checkpoint was claimed")
            catalog, data = self._catalog(row["catalog_version"]), self._data(row["data_path"])
            plan_json = json.loads(row["plan_json"])
        try:
            if plan_json.get("schema") == "p0-3b-inherited-pending-v1":
                state = self.cycle.get(sid, catalog, data)
                parent_compiled, child, inheritance = self._materialize_inherited(
                    catalog,
                    data,
                    state,
                    plan_json,
                )
                completed = self.cycle.advance_inherited(
                    sid,
                    catalog,
                    data,
                    _SubmittedDiagnosisOnly(diagnosis),
                    parent_compiled=parent_compiled,
                    compiled=child,
                    source_plan=plan_json["base_algorithm_plan"],
                    inheritance=inheritance,
                    inherited_intent=plan_json["inherited_intent"],
                )
            else:
                completed = self.cycle.advance(
                    sid,
                    catalog,
                    data,
                    _SubmittedProvider(plan_json, diagnosis),
                )
        except Exception:
            with self._connect() as db:
                db.execute(
                    "UPDATE stages SET phase='INTERRUPTED' WHERE session_id=? AND phase='RUNNING'",
                    (sid,),
                )
            raise
        with self._connect() as db:
            new_token = uuid4().hex
            next_phase = "COMPLETED" if completed["status"] == "COMPLETED" else "AWAITING_PLAN"
            committed = db.execute(
                """UPDATE stages SET phase=?,token=?,plan_json=NULL,
            plan_digest=NULL,context_digest=NULL WHERE session_id=? AND phase='RUNNING' """,
                (next_phase, new_token, sid),
            )
            if committed.rowcount != 1:
                raise CycleStateError("diagnosis checkpoint finalization conflict")
            self._record_submission(
                db,
                sid,
                "diagnosis",
                token,
                replay_request,
                new_token,
                next_phase,
                completed["completed_generations"],
            )
        # MCP-first shortcut: a complete research generation must carry its
        # measured experiment evidence into the NEXT LLM planning prompt.
        # Previously ChatGPT had to make an extra evaluate_* call and could
        # accidentally start the next generation from unmeasured hypotheses.
        # All comparison results use the existing immutable, idempotent S7
        # storage and the *same* development dataset as the original plan.
        return self._evaluated_reply(sid, completed["completed_generations"])

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

    def continue_verified_child(self, args: dict[str, Any]) -> dict[str, Any]:
        """Explicit GPT-directed sidecar mutation of a REPLAYED S7 child.

        This is research lineage only: never a counted generation or a
        retroactive alteration of immutable Cycle Evidence.
        """
        self._one(
            args,
            {
                "session_id",
                "generation",
                "checkpoint_token",
                "hypothesis_id",
                "child_strategy_hash",
                "continuation_intent",
            },
            {
                "session_id",
                "generation",
                "checkpoint_token",
                "hypothesis_id",
                "child_strategy_hash",
                "continuation_intent",
            },
        )
        sid, generation = args["session_id"], args["generation"]
        if (
            type(generation) is not int
            or not 1 <= generation <= 100
            or not isinstance(args["hypothesis_id"], str)
            or not isinstance(args["child_strategy_hash"], str)
            or len(args["child_strategy_hash"]) != 64
            or not isinstance(args["continuation_intent"], dict)
        ):
            raise ValueError("invalid successor source, identity or structured intent")
        key = content_hash(
            {
                "hypothesis_id": args["hypothesis_id"],
                "child_strategy_hash": args["child_strategy_hash"],
                "continuation_intent": args["continuation_intent"],
            }
        )
        with self._connect() as db:
            row, catalog, data, state = self._state(db, sid)
            if (
                row["phase"] != "AWAITING_PLAN"
                or row["token"] != args["checkpoint_token"]
                or state["status"] != "AWAITING_PROVIDER"
            ):
                raise CycleStateError("successor requires exact idle planning checkpoint")
            if generation > state["completed_generations"]:
                raise CycleStateError("successor source generation not committed")
            original = state["history"][generation - 1]
            stored = self._stored_experiment(db, sid, generation)
            if stored is None:
                raise CycleStateError("successor requires measured S7 experiment proof")
            prior = db.execute(
                "SELECT result_json,result_hash FROM successor_lineages "
                "WHERE session_id=? AND origin_generation=? AND request_hash=?",
                (sid, generation, key),
            ).fetchone()
            if prior is not None:
                result: dict[str, Any] = json.loads(prior["result_json"])
                if (
                    content_hash({k: v for k, v in result.items() if k != "report_hash"})
                    != prior["result_hash"]
                    or result.get("report_hash") != prior["result_hash"]
                ):
                    raise CycleStateError("stored successor lineage integrity failure")
                return result
        result = verified_child_successor(
            catalog,
            data,
            original,
            stored,
            hypothesis_id=args["hypothesis_id"],
            expected_child_strategy_hash=args["child_strategy_hash"],
            continuation_intent=args["continuation_intent"],
        )
        # Canonicalize tuple-backed audit records to stable JSON list types.
        result = json.loads(json.dumps(result, sort_keys=True))
        with self._connect() as db:
            locked = db.execute(
                "SELECT phase,token FROM stages WHERE session_id=?", (sid,)
            ).fetchone()
            if (
                locked is None
                or locked["phase"] != "AWAITING_PLAN"
                or locked["token"] != args["checkpoint_token"]
            ):
                raise CycleStateError("planning checkpoint changed during successor replay")
            db.execute(
                "INSERT OR IGNORE INTO successor_lineages "
                "(session_id,origin_generation,request_hash,result_json,result_hash) "
                "VALUES(?,?,?,?,?)",
                (sid, generation, key, json.dumps(result, sort_keys=True), result["report_hash"]),
            )
            check = db.execute(
                "SELECT result_json,result_hash FROM successor_lineages "
                "WHERE session_id=? AND origin_generation=? AND request_hash=?",
                (sid, generation, key),
            ).fetchone()
            assert check is not None
            stored_result = json.loads(check["result_json"])
            if stored_result != result or check["result_hash"] != result["report_hash"]:
                raise CycleStateError("successor persistence conflict")
        return result

    def evaluate_experiments(self, args: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a completed diagnosis against its frozen original strategy."""
        if "continuation_intent" in args or "hypothesis_id" in args:
            return self.continue_verified_child(args)
        self._one(args, {"session_id", "generation"}, {"session_id", "generation"})
        sid, generation = args["session_id"], args["generation"]
        if type(generation) is not int or not 1 <= generation <= 100:
            raise ValueError("generation must be integer 1-100")
        with self._connect() as db:
            _, catalog, data, state = self._state(db, sid)
            if generation > state["completed_generations"]:
                raise ValueError("generation is not complete")
            stored = self._stored_experiment(db, sid, generation)
            if stored is not None:
                if (
                    stored["original_generation_evidence_hash"]
                    != state["history"][generation - 1]["evidence_hash"]
                ):
                    raise CycleStateError("controlled experiment parent evidence mismatch")
                return stored
        original = state["history"][generation - 1]
        inherited_generation = original.get("inherited_strategy_ir") is not None
        if inherited_generation:
            inherited = self._inherited_from_evidence(catalog, data, original)
        else:
            plan = AlgorithmPlan.model_validate(original["algorithm_plan"])
            compiled = compile_algorithm_plan(catalog, plan, data)
            if compiled.compiled.strategy_hash != original["strategy_hash"]:
                raise CycleStateError("original strategy hash mismatch")
        hypotheses = [
            {
                "hypothesis_id": item["hypothesis_id"],
                "observed_ids": item["observed_ids"],
                "mechanism": item["mechanism"],
                "alternative": item["alternative"],
                "expected_metric": item["expected_metric"],
                "predicted_direction": item["predicted_direction"],
                "test_design": item["test_design"],
                "control": item["control"],
                "next_intent": item["proposed_intent"],
            }
            for item in original["experiments"]
        ]
        diagnostic = {
            "context_hash": original["diagnostic_context_hash"],
            "audit_hash": original["audit_hash"],
            "strategy_hash": original["strategy_hash"],
            "dataset_hash": original["dataset_hash"],
            "summary": original["analysis_summary"],
            "hypotheses": hypotheses,
        }
        if inherited_generation:
            report = compare_inherited_experiments(
                inherited,
                data,
                diagnostic,
                parent_proof_hash=original["inherited_parent"]["parent_selection_hash"],
            )
        else:
            report = compare_controlled_experiments(catalog, compiled, data, diagnostic)
        if (
            report.diagnostic_proposal_hash != original["diagnostic_proposal_hash"]
            or report.audit_hash != original["audit_hash"]
            or report.plan_hash != original["plan_hash"]
        ):
            raise CycleStateError("controlled experiment does not match original evidence")
        body = {
            "session_id": sid,
            "generation": generation,
            "original_generation_evidence_hash": original["evidence_hash"],
            "report": asdict(report),
            "study_scope": "REUSED_DEVELOPMENT_NON_PIT_NOT_CAUSAL_PROOF",
        }
        digest = content_hash(body)
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO experiment_reports "
                "(session_id,generation,report_json,report_hash) VALUES(?,?,?,?)",
                (sid, generation, json.dumps(body, sort_keys=True), digest),
            )
            verified = self._stored_experiment(db, sid, generation)
            if verified is None:
                raise CycleStateError("controlled experiment persistence failed")
            if verified["original_generation_evidence_hash"] != original["evidence_hash"]:
                raise CycleStateError("controlled experiment concurrent identity mismatch")
            db.execute(
                "UPDATE generation_timings SET end_utc=?, evidence_hash=? "
                "WHERE session_id=? AND generation=? AND end_utc IS NULL",
                (
                    datetime.now(timezone.utc).isoformat(),
                    original["evidence_hash"],
                    sid,
                    generation,
                ),
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
