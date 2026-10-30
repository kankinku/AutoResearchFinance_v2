"""Durable, externally GPT-directed checkpoints: exactly one authorized run per step.

No local LLM, broker access, silent retries, promotion, or sealed OOS queries.
A caller must submit a new typed ResearchIntent for each generation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

from application.chat_directed_research_service import ChatDirectedResearchService
from application.evaluation_service import EvaluationService
from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from core.features.registry import research_feature_specs
from core.integrity.hashes import content_hash
from experiments.candidate_generator import generate_candidates
from experiments.identity import semantic_strategy_hash
from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from orchestration.evaluation_runner import (
    ALLOWED_STRATEGY_SUFFIXES,
    resolve_project_input,
)
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent, intent_to_operations
from research.llm.guided_execution_preflight import require_costed_execution_change
from research.llm.guided_threshold_recommender import suggest_training_thresholds
from research.llm.guided_parent_inheritance import inherited_parent_from_evidence
from research.llm.guided_controlled_development import controlled_training_comparison
from research.llm.guided_director_brief import (
    build_director_brief,
    summarize_parent_outcomes,
    validate_director_decision,
)
from research.llm.guided_crossover import crossover_exit
from research.llm.guided_research_feedback import (
    check_proposal, summarize as summarize_guided_learning, training_outcome,
)
from strategy_ir.schema import StrategyIR
from research.policy import default_evaluation_thresholds, load_policy
from strategy_ir.normalizer import normalize_source


class GPTGuidedResearchService:
    """External-GPT checkpoint broker, separate from autonomous local batches."""

    def __init__(self, *, project_root: Path, state_dir: Path) -> None:
        self.root = project_root.resolve()
        self.state_dir = state_dir.resolve()
        self.db_path = self.state_dir / "system" / "gpt-guided-sessions.sqlite"

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
          CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, status TEXT NOT NULL, request_json TEXT NOT NULL,
            dataset_hash TEXT NOT NULL, file_sha256 TEXT NOT NULL,
            requested INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
            token TEXT, previous_run_id TEXT
          );
          CREATE TABLE IF NOT EXISTS steps (
            session_id TEXT NOT NULL, generation INTEGER NOT NULL,
            run_id TEXT NOT NULL UNIQUE, attempt_id TEXT NOT NULL,
            previous_run_id TEXT, failed_gates_json TEXT NOT NULL,
            PRIMARY KEY(session_id, generation)
          );
          CREATE TABLE IF NOT EXISTS guided_controlled_reports (
            session_id TEXT NOT NULL, generation INTEGER NOT NULL,
            run_id TEXT NOT NULL UNIQUE, proposal_hash TEXT NOT NULL,
            report_json TEXT NOT NULL, report_hash TEXT NOT NULL,
            PRIMARY KEY(session_id,generation)
          );
          CREATE TABLE IF NOT EXISTS guided_research_proposals (
            run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
            generation INTEGER NOT NULL, proposal_json TEXT NOT NULL,
            proposal_hash TEXT NOT NULL, status TEXT NOT NULL,
            UNIQUE(session_id, generation)
          );
          CREATE TABLE IF NOT EXISTS guided_execution_signatures (
            dataset_hash TEXT NOT NULL, execution_hash TEXT NOT NULL,
            session_id TEXT NOT NULL, generation INTEGER NOT NULL,
            run_id TEXT NOT NULL, status TEXT NOT NULL,
            PRIMARY KEY(dataset_hash, execution_hash)
          );
        """)
        existing = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
        for name in (
            "inflight_run_id",
            "inflight_attempt_id",
            "inflight_intent_hash",
            "inflight_semantic_hashes_json",
            "inflight_source_sha256",
            "inflight_execution_hashes_json",
            "inflight_parent_run_id",
            "inflight_parent_semantic_hash",
            "inflight_proposal_hash",
            "inflight_donor_run_id",
            "inflight_donor_semantic_hash",
        ):
            if name not in existing:
                try:
                    db.execute(f"ALTER TABLE sessions ADD COLUMN {name} TEXT")
                except sqlite3.OperationalError as exc:
                    # Concurrent first access may have applied the same migration.
                    if "duplicate column name" not in str(exc).lower():
                        raise
        return db

    @staticmethod
    def _integer(raw: object, name: str, minimum: int, maximum: int) -> int:
        if type(raw) is not int or not minimum <= raw <= maximum:
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
        return raw

    def start(self, args: dict[str, Any]) -> dict[str, object]:
        allowed = {
            "data_path",
            "generations",
            "method",
            "count",
            "seed",
            "min_trades",
            "min_annual_trades",
            "min_qqq_cagr_delta",
            "require_execution_change",
            "allow_verified_parent_inheritance",
            "allow_research_parent_inheritance",
            "adaptive_research_controller",
            "allow_two_parent_crossover",
            "benchmark_mode",
        }
        if set(args) - allowed:
            raise ValueError("unknown guided session arguments")
        p = resolve_project_input(self.root, args.get("data_path"), frozenset({".parquet"}))
        data = ParquetDataProvider.read(p)
        if DataZone(data.zone) is not DataZone.DEVELOPMENT:
            raise PermissionError("guided research uses development data only")
        thresholds = default_evaluation_thresholds()
        policy = load_policy(Path(__file__).resolve().parents[1] / "research" / "policy.yaml")
        minimum_trades = policy.evaluation.min_trade_count
        generations = self._integer(args.get("generations"), "generations", 1, 100)
        count = self._integer(args.get("count", 1), "count", 1, 64)
        seed = self._integer(args.get("seed", 0), "seed", 0, 2**31 - 101)
        method = args.get("method", "grid")
        if method not in {"grid", "random", "bayesian"}:
            raise ValueError("invalid generation method")
        min_trades = self._integer(
            args.get("min_trades", minimum_trades), "min_trades", minimum_trades, 100000
        )
        min_annual = self._integer(
            args.get("min_annual_trades", thresholds.min_annual_trades),
            "min_annual_trades",
            thresholds.min_annual_trades,
            100000,
        )
        qqq = args.get("min_qqq_cagr_delta", thresholds.min_qqq_cagr_delta)
        if (
            type(qqq) not in (float, int)
            or not isfinite(qqq)
            or qqq < thresholds.min_qqq_cagr_delta
        ):
            raise ValueError("QQQ hurdle cannot be relaxed below policy")
        require_execution_change = args.get("require_execution_change", False)
        if type(require_execution_change) is not bool:
            raise ValueError("require_execution_change must be boolean")
        allow_inheritance = args.get("allow_verified_parent_inheritance", False)
        if type(allow_inheritance) is not bool:
            raise ValueError("allow_verified_parent_inheritance must be boolean")
        if allow_inheritance and not require_execution_change:
            raise ValueError("inheritance requires strict execution-change policy")
        research_parent = args.get("allow_research_parent_inheritance", False)
        if type(research_parent) is not bool:
            raise ValueError("allow_research_parent_inheritance must be boolean")
        if research_parent and not require_execution_change:
            raise ValueError("research parent inheritance requires strict execution-change policy")
        adaptive_controller = args.get("adaptive_research_controller", False)
        if type(adaptive_controller) is not bool:
            raise ValueError("adaptive_research_controller must be boolean")
        if adaptive_controller and not research_parent:
            raise ValueError("adaptive controller requires research parent and strict execution opt-in")
        allow_crossover=args.get("allow_two_parent_crossover",False)
        if type(allow_crossover) is not bool:
            raise ValueError("allow_two_parent_crossover must be boolean")
        if allow_crossover and not (adaptive_controller and research_parent and require_execution_change):
            raise ValueError("two-parent crossover requires adaptive research, parent and strict-execution opt-in")
        benchmark_mode = args.get("benchmark_mode")
        if benchmark_mode not in (None, "QQQ_COSTED_NEXT_OPEN_DEV_V1"):
            raise ValueError("invalid guided benchmark mode")
        if benchmark_mode == "QQQ_COSTED_NEXT_OPEN_DEV_V1":
            if data.timeframe != "1d" or any(bar.symbol != "QQQ" for bar in data.bars):
                raise ValueError("local QQQ benchmark requires one daily QQQ symbol")
        request = {
            "benchmark_mode":benchmark_mode,
            "allow_verified_parent_inheritance":allow_inheritance,
            "allow_research_parent_inheritance":research_parent,
            "adaptive_research_controller":adaptive_controller,
            "allow_two_parent_crossover":allow_crossover,
            "require_execution_change": require_execution_change,
            "data_path": p.relative_to(self.root).as_posix(),
            "generations": generations,
            "method": method,
            "count": count,
            "seed": seed,
            "min_trades": min_trades,
            "min_annual_trades": min_annual,
            "min_qqq_cagr_delta": float(qqq),
        }
        session_id = uuid4().hex
        with self._connect() as db:
            db.execute(
                "INSERT INTO sessions "
                "(id,status,request_json,dataset_hash,file_sha256,requested,"
                "completed,token,previous_run_id) "
                "VALUES (?,?,?,?,?,?,0,?,NULL)",
                (
                    session_id,
                    "AWAITING_GPT",
                    json.dumps(request, sort_keys=True),
                    data.dataset_hash,
                    hashlib.sha256(p.read_bytes()).hexdigest(),
                    generations,
                    secrets.token_hex(16),
                ),
            )
        return self.get(session_id)

    def extend_completed_campaign(self, *, session_id: str, additional_generations: int,
                                  expected_completed_generations: int) -> dict[str, object]:
        """Audited in-place continuation of an exactly completed Guided campaign.

        Existing 1..N signed research proposals, costed fills, hashes and
        research parents are never replaced. The request can be extended only
        while completely idle, with CAS and a separately signed audit record.
        Research policy and development data remain byte-for-byte unchanged.
        """
        additional=self._integer(additional_generations,'additional_generations',1,99)
        original=self._integer(expected_completed_generations,'expected_completed_generations',1,199)
        # Validate all existing signed attempts and training controls before
        # mutating one word of campaign metadata.
        checkpoint=self.get(session_id)
        if (checkpoint['status']!='COMPLETED'
            or checkpoint['completed_generations']!=original
            or checkpoint['requested_generations']!=original
            or checkpoint['inflight_run_id'] is not None
            or checkpoint['orders_enabled'] is not False
            or checkpoint['sealed_oos_evaluated'] is not False
            or checkpoint['controlled_training_memory']['verified_generations']!=original
            or not checkpoint['allow_research_parent_inheritance']
            or not checkpoint['adaptive_research_controller']
            or not checkpoint['require_execution_change']):
            raise ValueError('EXTEND_REQUIRES_VERIFIED_FINISHED_STRICT_CAMPAIGN')
        new_total=original+additional
        if new_total>200:
            raise ValueError('EXTEND_EXCEEDS_MAX_200_GENERATIONS')
        row,request=self._read(session_id)
        from research.llm.guided_campaign_runner import GuidedCampaignRunner
        journal=GuidedCampaignRunner(self).audit(session_id)
        commits=[x for x in journal if x['event'] in (
            'GENERATION_COMMITTED','RECOVERED_COMMITTED_GENERATION')]
        if (len(commits)!=original or commits[-1]['generation']!=original
            or [x['generation'] for x in commits]!=list(range(1,original+1))):
            raise ValueError('EXTEND_CAMPAIGN_JOURNAL_NOT_CONTIGUOUS')
        source=resolve_project_input(self.root,request['data_path'],frozenset({'.parquet'}))
        if (hashlib.sha256(source.read_bytes()).hexdigest()!=row['file_sha256']
            or ParquetDataProvider.read(source).dataset_hash!=row['dataset_hash']):
            raise EvidenceIntegrityError('EXTEND_SOURCE_DATASET_CHANGED')
        old_hash=content_hash(request)
        new_request={**request,'generations':new_total}
        extension={
            'schema':'guided-in-place-campaign-extension-v1',
            'session_id':session_id,'from_generations':original,'to_generations':new_total,
            'additional_generations':additional,
            'previous_run_id':checkpoint['last_run_id'],
            'old_request_hash':old_hash,'new_request_hash':content_hash(new_request),
            'dataset_hash':row['dataset_hash'],
            'last_campaign_record_hash':journal[-1]['record_hash'],
            'training_control_count':original,
            'preserve_original_immutable_steps':True,
            'policy_unchanged':True,'sealed_oos_evaluated':False,'orders_enabled':False,
        }
        extension['extension_hash']=content_hash(extension)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("""CREATE TABLE IF NOT EXISTS guided_campaign_extensions (
                session_id TEXT NOT NULL, from_generations INTEGER NOT NULL,
                to_generations INTEGER NOT NULL, evidence_json TEXT NOT NULL,
                extension_hash TEXT NOT NULL,
                PRIMARY KEY(session_id,from_generations))""")
            still=db.execute('SELECT * FROM sessions WHERE id=?',(session_id,)).fetchone()
            if (still is None or still['completed']!=original or still['requested']!=original
                or still['status']!='COMPLETED' or still['request_json']!=row['request_json']
                or still['previous_run_id']!=checkpoint['last_run_id']
                or any(still[k] is not None for k in (
                    'inflight_run_id','inflight_attempt_id','inflight_proposal_hash'))):
                raise ValueError('EXTEND_CONCURRENT_CHANGE_OR_INFLIGHT')
            for table in ('steps','guided_controlled_reports','guided_research_proposals'):
                n=db.execute(f'SELECT COUNT(*) FROM {table} WHERE session_id=?',(session_id,)).fetchone()[0]
                if n!=original:
                    raise EvidenceIntegrityError('EXTEND_INCOMPLETE_SIGNED_ORIGINAL_HISTORY')
            db.execute("""INSERT INTO guided_campaign_extensions
                (session_id,from_generations,to_generations,evidence_json,extension_hash)
                VALUES (?,?,?,?,?)""", (session_id,original,new_total,
                json.dumps(extension,sort_keys=True),extension['extension_hash']))
            update=db.execute("""UPDATE sessions SET requested=?,request_json=?,
                status='AWAITING_GPT',token=? WHERE id=?
                AND completed=? AND requested=? AND status='COMPLETED' """,(
                new_total,json.dumps(new_request,sort_keys=True),
                secrets.token_hex(16),session_id,original,original))
            if update.rowcount!=1:
                raise ValueError('EXTEND_CHECKPOINT_CAS_FAILED')
        resumed=self.get(session_id)
        if (resumed['status']!='AWAITING_GPT' or resumed['generation']!=original+1
            or resumed['requested_generations']!=new_total
            or resumed['controlled_training_memory']['verified_generations']!=original):
            raise EvidenceIntegrityError('EXTEND_RESUMED_CHECKPOINT_MISMATCH')
        return {'extension':extension,'checkpoint':resumed}

    def suggest_thresholds(self, args: dict[str, Any]) -> dict[str, Any]:
        if set(args) - {"session_id", "source_path", "feature_id", "op"}:
            raise ValueError("unknown guided threshold calibration argument")
        session_id = args.get("session_id")
        row, request = self._read(session_id)
        source = resolve_project_input(
            self.root, args.get("source_path"), ALLOWED_STRATEGY_SUFFIXES
        )
        imported = normalize_source(source)
        if imported.strategy is None:
            raise ValueError("unknown threshold calibration strategy")
        data = resolve_project_input(self.root, request["data_path"], frozenset({".parquet"}))
        if hashlib.sha256(data.read_bytes()).hexdigest() != row["file_sha256"]:
            raise ValueError("guided dataset checksum changed")
        market = ParquetDataProvider.read(data)
        if market.dataset_hash != row["dataset_hash"]:
            raise ValueError("guided dataset identity changed")
        feature_id = args.get("feature_id")
        if not isinstance(feature_id, str):
            raise ValueError("feature_id required")
        report = suggest_training_thresholds(
            parent=imported.strategy, dataset=market, feature_id=feature_id,
            op=args.get("op", "greater_than")
        )
        return {"session_id":session_id, "source_path":source.relative_to(self.root).as_posix(), **report}

    def _read(self, session_id: str) -> tuple[sqlite3.Row, dict[str, Any]]:
        if not isinstance(session_id, str) or len(session_id) != 32:
            raise ValueError("invalid guided session ID")
        with self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise ValueError("guided session not found")
        return row, json.loads(row["request_json"])

    def _evaluated_semantic_hashes(self, session_id: str, dataset_hash: str) -> frozenset[str]:
        """Reconstruct previously evaluated executable IR identities from immutable Evidence.

        Only steps committed to this GPT session count as its prior generations.
        Missing/corrupt Evidence must stop research, not allow a duplicate retry.
        """
        with self._connect() as db:
            steps = db.execute(
                "SELECT generation, run_id, attempt_id FROM steps "
                "WHERE session_id=? ORDER BY generation",
                (session_id,),
            ).fetchall()
        if not steps:
            return frozenset()
        events = EvidenceStore(self.state_dir).events()
        lookup = {
            (event["payload"]["research_run_id"], event["payload"]["attempt_id"]): event["payload"]
            for event in events
            if event["kind"] == "attempt"
        }
        hashes: set[str] = set()
        for step in steps:
            attempt = lookup.get((step["run_id"], step["attempt_id"]))
            if attempt is None or attempt.get("status") != "COMPLETED":
                raise EvidenceIntegrityError(
                    "guided previous generation has missing attempt evidence"
                )
            candidates = attempt.get("candidates", [])
            if not candidates or attempt.get("verification") is not None:
                raise EvidenceIntegrityError("guided previous generation has unverified candidates")
            for candidate in candidates:
                digest = candidate.get("semantic_strategy_hash")
                if (
                    candidate.get("dataset_hash") != dataset_hash
                    or not isinstance(digest, str)
                    or len(digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in digest)
                ):
                    raise EvidenceIntegrityError("guided previous strategy evidence is invalid")
                hashes.add(digest)
        return frozenset(hashes)

    def _verified_inherited_parent(
        self, session_id: str, ancestor_generation: int, dataset_hash: str
    ) -> tuple[object,str,str]:
        if type(ancestor_generation) is not int or ancestor_generation < 1:
            raise ValueError("inherit_from_generation must be a positive integer")
        with self._connect() as db:
            step = db.execute(
                "SELECT run_id,attempt_id FROM steps WHERE session_id=? AND generation=?",
                (session_id,ancestor_generation),
            ).fetchone()
        if step is None:
            raise ValueError("INHERITED_PARENT_MUST_BE_COMPLETED_PRIOR_GENERATION")
        matches = [
            item["payload"] for item in EvidenceStore(self.state_dir).events()
            if item["kind"]=="attempt" and item["payload"].get("research_run_id")==step["run_id"]
            and item["payload"].get("attempt_id")==step["attempt_id"]
        ]
        if len(matches)!=1:
            raise EvidenceIntegrityError("INHERITED_PARENT_ATTEMPT_PROVENANCE_MISSING")
        strategy,identity=inherited_parent_from_evidence(attempt=matches[0],dataset_hash=dataset_hash)
        return strategy,identity,step["run_id"]

    def _learning_history(self, session_id: str, dataset_hash: str) -> list[dict[str, Any]]:
        """Read only signed session steps; include rejected candidates in the analysis."""
        with self._connect() as db:
            steps = db.execute(
                "SELECT generation,run_id,attempt_id FROM steps WHERE session_id=? ORDER BY generation",
                (session_id,),
            ).fetchall()
            proposals = {
                row["run_id"]:dict(row) for row in db.execute(
                    "SELECT run_id,session_id,generation,proposal_json,proposal_hash,status "
                    "FROM guided_research_proposals WHERE session_id=?",(session_id,)
                )
            }
        if not steps:
            return []
        events=EvidenceStore(self.state_dir).events()
        all_attempts={
            (e["payload"].get("research_run_id"),e["payload"].get("attempt_id")):e["payload"]
            for e in events if e["kind"]=="attempt"
        }
        run_events={e["payload"].get("research_run_id"):e["payload"]
                    for e in events if e["kind"]=="run"}
        history=[]
        for position,step in enumerate(steps,1):
            if step["generation"]!=position:
                raise EvidenceIntegrityError("noncontiguous guided research learning history")
            attempt=all_attempts.get((step["run_id"],step["attempt_id"]))
            if attempt is None:
                raise EvidenceIntegrityError("guided learning attempt is missing")
            for c in attempt.get("candidates",[]):
                if c.get("dataset_hash")!=dataset_hash:
                    raise EvidenceIntegrityError("guided learning attempt dataset mismatch")
            obj=proposals.get(step["run_id"])
            entry={"run_id":step["run_id"],"attempt_id":step["attempt_id"],
                   "attempt":attempt,"proposal_verified":False,"proposal_hash":None}
            if obj is not None:
                if (obj["generation"]!=position or obj["status"]!="COMMITTED"):
                    raise EvidenceIntegrityError("guided learning proposal not finalized")
                proposal=json.loads(obj["proposal_json"])
                check_proposal(proposal,expected_hash=obj["proposal_hash"])
                run=run_events.get(step["run_id"])
                if run is None or run.get("settings",{}).get("guided_proposal_hash")!=obj["proposal_hash"]:
                    raise EvidenceIntegrityError("guided learning proposal missing run Evidence binding")
                recorded={x["semantic_strategy_hash"] for x in attempt.get("candidates",[])}
                proposed={x["semantic_strategy_hash"] for x in proposal["candidates"]}
                if recorded!=proposed:
                    raise EvidenceIntegrityError("guided learning proposal not tied to evaluated candidate")
                cross=proposal.get("crossover_proof")
                if cross is not None:
                    for label in ("primary","donor"):
                        past=next((h for h in history if h["run_id"]==cross.get(f"{label}_run_id")),None)
                        if past is None or not past.get("proposal_verified"):
                            raise EvidenceIntegrityError("CROSSOVER_PARENT_EVIDENCE_NOT_COMMITTED_PRIOR")
                        expected_hash=cross["primary_semantic_hash" if label=="primary" else "donor_semantic_hash"]
                        if expected_hash not in {c["semantic_strategy_hash"] for c in past["attempt"].get("candidates",[])}:
                            raise EvidenceIntegrityError("CROSSOVER_PARENT_EVIDENCE_SEMANTICS_DISAGREE")
                    if cross["primary_generation"]>=position or cross["donor_generation"]>=position:
                        raise EvidenceIntegrityError("CROSSOVER_FUTURE_PARENT_FORBIDDEN")
                entry.update(proposal_verified=True,proposal_hash=obj["proposal_hash"],proposal=proposal)
            history.append(entry)
        return history

    def _research_parent(self, session_id: str, ancestor_generation: int,
                         dataset_hash: str) -> tuple[StrategyIR,str,str]:
        """Permit *failed* candidates for DEVELOPMENT hypotheses, never approval.

        Parent choice must be explicit from GPT, pinned before child evaluation,
        selected solely from pre-test training folds and exact immutable IR.
        """
        if type(ancestor_generation) is not int or ancestor_generation < 1:
            raise ValueError("RESEARCH_PARENT_INVALID_GENERATION")
        history=self._learning_history(session_id,dataset_hash)
        if ancestor_generation>len(history):
            raise ValueError("RESEARCH_PARENT_NOT_A_PRIOR_COMPLETED_GENERATION")
        source=history[ancestor_generation-1]
        if not source.get("proposal_verified"):
            raise ValueError("RESEARCH_PARENT_ORIGINAL_IR_NOT_PERSISTED")
        attempt=source["attempt"]
        if len(attempt.get("candidates",[]))!=1:
            raise ValueError("RESEARCH_PARENT_AMBIGUOUS_CANDIDATES")
        candidate=attempt["candidates"][0]
        trained=training_outcome(attempt,candidate)
        if not trained["train_folds_observed"]:
            raise ValueError("RESEARCH_PARENT_TRAINING_PROVENANCE_UNAVAILABLE")
        strategy_record=source["proposal"]["candidates"][0]
        if strategy_record["semantic_strategy_hash"]!=candidate["semantic_strategy_hash"]:
            raise ValueError("RESEARCH_PARENT_STRATEGY_IDENTITY_MISMATCH")
        return (StrategyIR.model_validate(strategy_record["strategy_ir"]),
                strategy_record["semantic_strategy_hash"],source["run_id"])

    def _controlled_reports(self,session_id:str, dataset_hash:str) -> list[dict[str,Any]]:
        with self._connect() as db:
            rows=db.execute(
                "SELECT c.generation,c.run_id,c.proposal_hash,c.report_json,c.report_hash,"
                " p.proposal_hash,st.run_id "
                "FROM guided_controlled_reports c "
                "JOIN steps st ON st.session_id=c.session_id AND st.generation=c.generation "
                "JOIN guided_research_proposals p ON p.run_id=c.run_id AND p.session_id=c.session_id "
                "WHERE c.session_id=? ORDER BY c.generation",(session_id,)
            ).fetchall()
        out=[]
        for item in rows:
            report=json.loads(item["report_json"])
            signed=report.pop("report_hash",None)
            if (signed!=item["report_hash"] or content_hash(report)!=signed
                or item["run_id"]!=report.get("run_id")
                or item["run_id"]!=item[6]
                or item["proposal_hash"]!=item[5]
                or report.get("proposal_hash")!=item["proposal_hash"]
                or report.get("original_dataset_hash")!=dataset_hash
                or report.get("sealed_oos_evaluated") is not False
                or report.get("orders_enabled") is not False):
                raise EvidenceIntegrityError("guided controlled report integrity violation")
            report["report_hash"]=signed
            out.append({"generation":item["generation"],**report})
        return out

    def _record_training_control(self,session_id:str,generation:int) -> dict[str,Any]:
        row,request=self._read(session_id)
        if not request.get("allow_research_parent_inheritance",False):
            raise ValueError("CONTROL_SESSION_OPT_IN_REQUIRED")
        if type(generation) is not int or not 1<=generation<=row["completed"]:
            raise ValueError("CONTROL_ONLY_COMMITTED_GENERATIONS")
        with self._connect() as db:
            step=db.execute("SELECT run_id,attempt_id FROM steps WHERE session_id=? AND generation=?",
                            (session_id,generation)).fetchone()
            raw=db.execute("SELECT proposal_json,proposal_hash,status FROM guided_research_proposals "
                           "WHERE session_id=? AND generation=?",(session_id,generation)).fetchone()
        if step is None or raw is None or raw["status"]!="COMMITTED":
            raise EvidenceIntegrityError("CONTROL_PRECOMMIT_STRATEGY_OR_RUN_NOT_AVAILABLE")
        source=self._learning_history(session_id,row["dataset_hash"])[generation-1]
        if (not source.get("proposal_verified") or source["run_id"]!=step["run_id"]
            or source.get("proposal_hash")!=raw["proposal_hash"]):
            raise EvidenceIntegrityError("CONTROL_ORIGINAL_RUN_PROPOSAL_NOT_ATTESTED")
        for known in self._controlled_reports(session_id,row["dataset_hash"]):
            if known["generation"]==generation:
                if known["run_id"]!=step["run_id"] or known["proposal_hash"]!=raw["proposal_hash"]:
                    raise EvidenceIntegrityError("CONTROL_CACHED_REPORT_EVIDENCE_MISMATCH")
                return known
        matched=[source["attempt"]]
        if matched[0]["attempt_id"]!=step["attempt_id"]:
            raise EvidenceIntegrityError("CONTROL_IMMUTABLE_ATTEMPT_NOT_FOUND")
        data=resolve_project_input(self.root,request["data_path"],frozenset({".parquet"}))
        if hashlib.sha256(data.read_bytes()).hexdigest()!=row["file_sha256"]:
            raise EvidenceIntegrityError("CONTROL_DATA_FILE_CHANGED")
        market=ParquetDataProvider.read(data)
        if market.dataset_hash!=row["dataset_hash"] or DataZone(market.zone) is not DataZone.DEVELOPMENT:
            raise EvidenceIntegrityError("CONTROL_PINNED_DEVELOPMENT_DATA_MISMATCH")
        report=controlled_training_comparison(
            proposal=json.loads(raw["proposal_json"]),proposal_hash=raw["proposal_hash"],
            attempt=matched[0],market=market,expected_run_id=step["run_id"])
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO guided_controlled_reports "
                       "(session_id,generation,run_id,proposal_hash,report_json,report_hash) "
                       "VALUES(?,?,?,?,?,?)",(session_id,generation,step["run_id"],
                       raw["proposal_hash"],json.dumps(report,sort_keys=True),report["report_hash"]))
        verified=[x for x in self._controlled_reports(session_id,row["dataset_hash"])
                  if x["generation"]==generation]
        if len(verified)!=1 or verified[0]["report_hash"]!=report["report_hash"]:
            raise EvidenceIntegrityError("CONTROL_CONCURRENT_REPORT_MISMATCH")
        return verified[0]

    def training_control(self,args:dict[str,Any]) -> dict[str,Any]:
        if set(args)!={"session_id","generation"}:
            raise ValueError("controlled training replay requires session_id,generation")
        return self._record_training_control(args["session_id"],args["generation"])

    def _cross_session_learning(self, session_id: str, dataset_hash: str) -> dict[str, Any]:
        with self._connect() as db:
            current=db.execute("SELECT rowid FROM sessions WHERE id=?",(session_id,)).fetchone()
            if current is None:
                raise ValueError("unknown session")
            previous=db.execute("SELECT id FROM sessions WHERE dataset_hash=? AND rowid<? AND completed>0 ORDER BY rowid DESC LIMIT 3",(dataset_hash,current[0])).fetchall()
        predecessors=[x[0] for x in reversed(previous)]
        combined=[]
        for sid in predecessors:
            combined.extend(self._learning_history(sid,dataset_hash))
        context=summarize_guided_learning(combined,dataset_hash=dataset_hash)
        return {"schema":"guided-prior-session-feedback-v1",
                "source_sessions":predecessors,
                "prior_evaluated_candidates":context["evaluated_candidates"],
                "prior_failed_candidates":context["failed_candidates_included"],
                "prior_failure_gate_counts":context["failure_gate_counts"],
                "suggested_controlled_hypotheses":context["suggested_controlled_hypotheses"],
                "evidence_digest":context["evidence_digest"],
                "research_parent_cross_session_allowed":False,
                "production_approval":False}

    def _count_execution_signatures(self, dataset_hash: str) -> int:
        with self._connect() as db:
            return int(db.execute(
                "SELECT count(*) FROM guided_execution_signatures WHERE dataset_hash=?",
                (dataset_hash,),
            ).fetchone()[0])

    def get(self, session_id: str) -> dict[str, object]:
        row, request = self._read(session_id)
        with self._connect() as db:
            steps = db.execute(
                "SELECT * FROM steps WHERE session_id=? ORDER BY generation", (session_id,)
            ).fetchall()
        history = [
            {
                "generation": s["generation"],
                "run_id": s["run_id"],
                "previous_run_id": s["previous_run_id"],
                "attempt_id": s["attempt_id"],
                "failed_gates": json.loads(s["failed_gates_json"]),
            }
            for s in steps
        ]
        waiting = row["status"] == "AWAITING_GPT"
        previously_evaluated = self._evaluated_semantic_hashes(session_id, row["dataset_hash"])
        controls=self._controlled_reports(session_id,row["dataset_hash"])
        gains=sum(x["result_observation"]=="PARENT_CHILD_TRAIN_NET_GAIN"
                  for r in controls for x in r["comparisons"])
        losses=sum(x["result_observation"]=="PARENT_CHILD_TRAIN_NET_LOSS"
                   for r in controls for x in r["comparisons"])
        signal_change=sum(x["execution_change_kind"]=="SIGNAL_TIMING_CHANGED"
                          for r in controls for x in r["comparisons"])
        only_size=sum(x["execution_change_kind"]=="EXECUTION_SIZE_OR_COST_CHANGED"
                      for r in controls for x in r["comparisons"])
        control_summary={
            "schema":"guided-training-controlled-memory-v1",
            "verified_generations":len(controls),"observed_train_gains":gains,
            "observed_train_losses":losses,"changed_signal_timing":signal_change,
            "size_or_cost_only_changes":only_size,
            "two_parent_controls_verified":sum(len(r.get("crossover_donor_comparisons") or []) for r in controls),
            "last_three_control_results":[{
                "generation":item["generation"],
                "donor_parent_controls":[{
                    "donor_run_id":x["donor_run_id"],
                    "net_return_delta_vs_donor":x["net_return_delta_vs_donor"],
                    "donor_costs":x["donor_costs"],"child_costs":x["child_costs"],
                    "added_events_vs_donor":x["added_events_vs_donor"],
                    "removed_events_vs_donor":x["removed_events_vs_donor"],
                    "causal_status":"NOT_ESTABLISHED",
                } for x in (item.get("crossover_donor_comparisons") or [])],
                "report_hash":item["report_hash"],
                "comparisons":[{
                    "result_observation":c["result_observation"],
                    "net_total_return_delta":c["net_total_return_delta"],
                    "execution_change_kind":c["execution_change_kind"],
                    "added_events":c["added_events"],"removed_events":c["removed_events"],
                    "child_costs":c["child_costs"],"parent_costs":c["parent_costs"],
                    "development_window_deltas":[w["net_return_delta"] for w in c["development_windows"]],
                } for c in item["comparisons"]],
            } for item in controls[-3:]],
            "next_experiment_priority":(
                "TRY_SINGLE_ENTRY_EXIT_TIMING_ABLATION" if only_size>=2 and signal_change==0 else
                "INVESTIGATE_REPEATED_TRAINING_NET_LOSSES_WITH_FIXED_CONTROL" if losses>gains else
                "RETEST_TRAINING_GAINS_AGAINST_COMPETING_EXPLANATIONS" if gains else
                "EXPLORE_AND_FORM_EXPLICIT_CONTROLLED_HYPOTHESIS"),
            "training_only_observations_not_production_approval":True,
            "causal_status":"NOT_ESTABLISHED","sealed_oos_evaluated":False,
        }
        signed_history = self._learning_history(session_id,row["dataset_hash"])
        if request.get("adaptive_research_controller", False):
            # Finalization calls get() before the newest training control is
            # committed. Only signed contiguous control-backed history ranks
            # parents; submit still blocks whenever the last control is missing.
            control_summary["parent_outcomes"] = summarize_parent_outcomes(
                history=signed_history[:len(controls)], controls=controls)
        current_learning = summarize_guided_learning(
            signed_history,
            dataset_hash=row["dataset_hash"],
        )
        director_brief = (
            build_director_brief(
                session_id=session_id,
                generation=row["completed"]+1,
                checkpoint_token=row["token"] if waiting else None,
                history=self._learning_history(session_id,row["dataset_hash"]),
                learning=current_learning,
                controlled=control_summary,
            )
            if request.get("adaptive_research_controller",False) else None
        )
        campaign_summary=None
        if request.get("adaptive_research_controller",False):
            from research.llm.guided_campaign_runner import GuidedCampaignRunner
            journal=GuidedCampaignRunner(self).audit(session_id)
            campaign_summary={
                "schema":"guided-resumable-campaign-status-v1",
                "journal_verified_records":len(journal),
                "logged_generation_commits":sum(r["event"] in {
                    "GENERATION_COMMITTED","RECOVERED_COMMITTED_GENERATION"
                } for r in journal),
                "precommit_rejections":sum(r["event"]=="PRECOMMIT_REJECTED" for r in journal),
                "recovered_commits_without_evaluator_replay":sum(
                    r["event"]=="RECOVERED_COMMITTED_GENERATION" for r in journal),
                "last_journal_event":journal[-1]["event"] if journal else None,
                "next_action":"EXTERNAL_GPT_SUBMIT_OR_RESUME" if waiting else "REVIEW_CHECKPOINT",
                "background_llm_worker":False,
                "model_owns_each_next_research_decision":True,
            }
        return {
            "session_id": session_id,
            "status": row["status"],
            "requested_generations": row["requested"],
            "completed_generations": row["completed"],
            "generation": row["completed"] + 1 if waiting else None,
            "checkpoint_token": row["token"] if waiting else None,
            "last_run_id": row["previous_run_id"],
            "inflight_run_id": row["inflight_run_id"],
            "inflight_attempt_id": row["inflight_attempt_id"],
            "previous_failed_gates": history[-1]["failed_gates"] if history else [],
            "previous_evaluated_strategies": len(previously_evaluated),
            "recorded_execution_signatures": self._count_execution_signatures(row["dataset_hash"]),
            "previous_semantic_strategy_hashes": sorted(previously_evaluated),
            "research_inputs": {
                "data_path": request["data_path"],
                "method": request["method"],
                "count": request["count"],
            },
            "next_action": (
                "GPT_SUBMIT_TYPED_INTENT"
                if waiting
                else "RECONCILE_AFTER_WORKER_STOPPED"
                if row["status"] == "EXECUTING"
                else "OPERATOR_REVIEW_OR_RECONCILE"
                if row["status"] == "INTERRUPTED"
                else "NONE"
            ),
            "history": history,
            "orders_enabled": False,
            "sealed_oos_evaluated": False,
            "validation_scope": "REUSED_DEVELOPMENT_DATA_NOT_INDEPENDENT_OOS",
            "llm_controller": "external_mcp_client_each_generation",
            "require_execution_change": request.get("require_execution_change", False),
            "benchmark_mode": request.get("benchmark_mode"),
            "allow_verified_parent_inheritance": request.get("allow_verified_parent_inheritance", False),
            "allow_research_parent_inheritance": request.get("allow_research_parent_inheritance",False),
            "adaptive_research_controller":request.get("adaptive_research_controller",False),
            "allow_two_parent_crossover":request.get("allow_two_parent_crossover",False),
            "research_director_brief":director_brief,
            "campaign_status":campaign_summary,
            "learning_feedback":current_learning,
            "cross_session_learning":self._cross_session_learning(session_id,row["dataset_hash"]),
            "controlled_training_memory":control_summary,
        }

    def _inspect_inflight(self, row: sqlite3.Row) -> tuple[str, list[str]]:
        """Accept only the exact terminal evaluator run reserved before CAS."""
        run_id = row["inflight_run_id"]
        attempt_id = row["inflight_attempt_id"]
        if not run_id or not attempt_id:
            return "LEGACY_INFLIGHT_UNTRACKED", []
        events = [
            e
            for e in EvidenceStore(self.state_dir).events()
            if e["payload"]["research_run_id"] == run_id
        ]
        if not events:
            return "INCOMPLETE_OR_MISSING_EVIDENCE", []
        groups: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            groups.setdefault(event["kind"], []).append(event["payload"])
        if len(groups.get("run", [])) != 1:
            return "EVIDENCE_IDENTITY_MISMATCH", []
        manifest = groups.get("manifest", [])
        attempts = groups.get("attempt", [])
        generations = groups.get("generation", [])
        ends = groups.get("end", [])
        request = json.loads(row["request_json"])
        run = groups["run"][0]
        expected_hashes = json.loads(row["inflight_semantic_hashes_json"] or "[]")
        expected_settings = {
            "guided_proposal_hash":row["inflight_proposal_hash"],
            "inherited_parent_run_id":row["inflight_parent_run_id"],
            "inherited_parent_semantic_hash":row["inflight_parent_semantic_hash"],
            "crossover_donor_run_id":row["inflight_donor_run_id"],
            "crossover_donor_semantic_hash":row["inflight_donor_semantic_hash"],
            "guided_session_id": row["id"],
            "guided_generation": row["completed"] + 1,
            "intent_hash": row["inflight_intent_hash"],
            "previous_research_run_id": row["previous_run_id"],
            "expected_semantic_hashes": expected_hashes,
        }
        settings = run.get("settings")
        if (
            not isinstance(settings, dict)
            or any(settings.get(k) != v for k, v in expected_settings.items())
            or run.get("requested_generations") != 1
            or run.get("seed") != request["seed"] + row["completed"]
            or settings.get("source_sha256") != row["inflight_source_sha256"]
        ):
            return "EVIDENCE_IDENTITY_MISMATCH", []
        if row["inflight_proposal_hash"] is not None:
            with sqlite3.connect(f"file:{self.db_path.resolve()}?mode=ro",uri=True) as audit_db:
                signed=audit_db.execute(
                    "SELECT proposal_json,proposal_hash,status FROM guided_research_proposals "
                    "WHERE session_id=? AND run_id=?",(row["id"],run_id)
                ).fetchone()
            if (signed is None or signed[1]!=row["inflight_proposal_hash"]
                    or signed[2]!="RESERVED"):
                return "RESEARCH_PROPOSAL_PROVENANCE_MISSING", []
            try:
                bound=check_proposal(json.loads(signed[0]),expected_hash=signed[1])
            except (ValueError,TypeError,KeyError):
                return "RESEARCH_PROPOSAL_HASH_INVALID", []
            if (bound.get("run_id")!=run_id or bound.get("session_id")!=row["id"]
                    or bound.get("dataset_hash")!=row["dataset_hash"]
                    or {c["semantic_strategy_hash"] for c in bound["candidates"]}
                    != set(expected_hashes)):
                return "RESEARCH_PROPOSAL_CANDIDATE_IDENTITY_INVALID", []
        if not ends or not generations or not attempts or not manifest:
            return "INCOMPLETE_OR_MISSING_EVIDENCE", []
        if len(manifest) != 1 or len(attempts) != 1 or len(generations) != 1 or len(ends) != 1:
            return "EVIDENCE_IDENTITY_MISMATCH", []
        attempt = attempts[0]
        if (
            attempt.get("attempt_id") != attempt_id
            or attempt.get("generation") != 1
            or generations[0].get("generation") != 1
            or generations[0].get("attempt_id") != attempt_id
        ):
            return "EVIDENCE_IDENTITY_MISMATCH", []
        if (
            ends[0].get("status") != "COMPLETED"
            or generations[0].get("status") != "COMPLETED"
            or attempt.get("status") != "COMPLETED"
            or attempt.get("verification") is not None
        ):
            return "INCOMPLETE_OR_MISSING_EVIDENCE", []
        candidates = attempt.get("candidates", [])
        if (
            not candidates
            or len(candidates) != len(expected_hashes)
            or {c.get("semantic_strategy_hash") for c in candidates} != set(expected_hashes)
            or any(c.get("dataset_hash") != row["dataset_hash"] for c in candidates)
        ):
            return "EVIDENCE_IDENTITY_MISMATCH", []
        return "VERIFIED_COMPLETED_EVIDENCE", sorted(
            {gate for candidate in candidates for gate in candidate.get("failed_gates", [])}
        )

    def _finalize_inflight(self, session_id: str) -> dict[str, object]:
        """Atomically adopt immutable, fully complete Evidence without reevaluation."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None or row["status"] not in {"EXECUTING", "INTERRUPTED"}:
                raise ValueError("inflight guided session no longer awaiting reconciliation")
            verdict, failed_gates = self._inspect_inflight(row)
            if verdict != "VERIFIED_COMPLETED_EVIDENCE":
                raise ValueError(f"unverifiable guided Evidence: {verdict}")
            execution_hashes = json.loads(row["inflight_execution_hashes_json"] or "[]")
            if json.loads(row["request_json"]).get("require_execution_change", False):
                expected = json.loads(row["inflight_semantic_hashes_json"] or "[]")
                if len(execution_hashes) != len(expected) or len(set(execution_hashes)) != len(expected):
                    raise EvidenceIntegrityError("guided execution trace hashes missing or duplicated")
                actual = db.execute(
                    "SELECT execution_hash FROM guided_execution_signatures "
                    "WHERE session_id=? AND run_id=? AND status='RESERVED'",
                    (session_id, row["inflight_run_id"]),
                ).fetchall()
                if {r[0] for r in actual} != set(execution_hashes):
                    raise EvidenceIntegrityError("guided reserved execution identities missing")
            generation = row["completed"] + 1
            final = generation == row["requested"]
            db.execute(
                "INSERT INTO steps VALUES(?,?,?,?,?,?)",
                (
                    session_id,
                    generation,
                    row["inflight_run_id"],
                    row["inflight_attempt_id"],
                    row["previous_run_id"],
                    json.dumps(failed_gates, sort_keys=True),
                ),
            )
            if row["inflight_proposal_hash"] is not None:
                updated_proposal=db.execute(
                    "UPDATE guided_research_proposals SET status='COMMITTED' "
                    "WHERE session_id=? AND run_id=? AND proposal_hash=? AND status='RESERVED'",
                    (session_id,row["inflight_run_id"],row["inflight_proposal_hash"]),
                )
                if updated_proposal.rowcount!=1:
                    raise EvidenceIntegrityError("guided proposal identity not committed")
            if execution_hashes:
                updated = db.execute(
                    "UPDATE guided_execution_signatures SET status='COMMITTED' "
                    "WHERE session_id=? AND run_id=? AND status='RESERVED'",
                    (session_id, row["inflight_run_id"]),
                )
                if updated.rowcount != len(execution_hashes):
                    raise EvidenceIntegrityError("incomplete guided execution identity commit")
            db.execute(
                "UPDATE sessions SET completed=?, status=?, token=?, previous_run_id=?,"
                " inflight_run_id=NULL, inflight_attempt_id=NULL,"
                " inflight_intent_hash=NULL, inflight_semantic_hashes_json=NULL,"
                " inflight_source_sha256=NULL, inflight_execution_hashes_json=NULL, "
                "inflight_parent_run_id=NULL, inflight_parent_semantic_hash=NULL,"
                "inflight_proposal_hash=NULL, inflight_donor_run_id=NULL,"
                "inflight_donor_semantic_hash=NULL WHERE id=?",
                (
                    generation,
                    "COMPLETED" if final else "AWAITING_GPT",
                    None if final else secrets.token_hex(16),
                    row["inflight_run_id"],
                    session_id,
                ),
            )
        return self.get(session_id)

    def reconcile(self, session_id: str) -> dict[str, object]:
        """Explicit, idempotent crash reconciliation. Never launch an evaluator."""
        row, _request = self._read(session_id)
        if row["status"] not in {"EXECUTING", "INTERRUPTED"}:
            if (_request.get("allow_research_parent_inheritance",False)
                    and row["completed"]>0):
                self._record_training_control(session_id,row["completed"])
            return {**self.get(session_id), "reconciliation": "ALREADY_SETTLED"}
        verdict, _failed = self._inspect_inflight(row)
        if verdict == "VERIFIED_COMPLETED_EVIDENCE":
            return {**self._finalize_inflight(session_id), "reconciliation": verdict}
        with self._connect() as db:
            db.execute(
                "UPDATE sessions SET status='INTERRUPTED' WHERE id=? AND status='EXECUTING'",
                (session_id,),
            )
        return {**self.get(session_id), "reconciliation": verdict}

    def submit(self, args: dict[str, Any]) -> dict[str, object]:
        allowed = {"session_id", "checkpoint_token", "generation", "source_path", "intent", "inherit_from_generation", "research_parent_generation", "research_decision", "crossover_donor_generation"}
        if set(args) - allowed:
            raise ValueError("guided generation cannot override fixed evaluation gates or dataset")
        session_id = args.get("session_id")
        if not isinstance(session_id, str):
            raise ValueError("guided session ID is required")
        row, request = self._read(session_id)
        if request.get("allow_research_parent_inheritance",False) and row["completed"]>0:
            completed_control={r["generation"] for r in self._controlled_reports(session_id,row["dataset_hash"])}
            if row["completed"] not in completed_control:
                raise ValueError("CONTROL_PREVIOUS_GENERATION_REQUIRED_CALL_RECONCILE")
        token = args.get("checkpoint_token")
        generation = args.get("generation")
        if (
            row["status"] != "AWAITING_GPT"
            or not isinstance(token, str)
            or not secrets.compare_digest(token, row["token"] or "")
            or type(generation) is not int
            or generation != row["completed"] + 1
        ):
            raise ValueError("stale checkpoint or generation already executing/completed")
        research_decision = args.get("research_decision")
        if request.get("adaptive_research_controller",False):
            if not isinstance(research_decision,dict):
                raise ValueError("DIRECTOR_RESEARCH_DECISION_REQUIRED")
            current_brief = self.get(session_id)["research_director_brief"]
            verified_decision = validate_director_decision(
                decision=research_decision,brief=current_brief,
                requested_parent_generation=args.get("research_parent_generation"),
            )
        elif research_decision is not None:
            raise ValueError("DIRECTOR_SESSION_OPT_IN_REQUIRED")
        else:
            verified_decision = None
        donor_generation=args.get("crossover_donor_generation")
        if donor_generation is not None:
            if not request.get("allow_two_parent_crossover",False):
                raise ValueError("CROSSOVER_SESSION_OPT_IN_REQUIRED")
            if (type(donor_generation) is not int or donor_generation>=generation
                or donor_generation<1 or donor_generation==args.get("research_parent_generation")):
                raise ValueError("CROSSOVER_INVALID_DONOR_GENERATION")
            if (verified_decision is None
                or verified_decision["research_mode"]!="CONTRAST_PARENTS"
                or verified_decision["contrast_parent_generation"]!=donor_generation
                or verified_decision["research_parent_generation"] is None):
                raise ValueError("CROSSOVER_GPT_DECISION_MISMATCH")
        elif verified_decision and verified_decision["research_mode"]=="CONTRAST_PARENTS" and request.get("allow_two_parent_crossover",False):
            raise ValueError("CROSSOVER_EXPLICIT_DONOR_REQUIRED")
        data = resolve_project_input(self.root, request["data_path"], frozenset({".parquet"}))
        if hashlib.sha256(data.read_bytes()).hexdigest() != row["file_sha256"]:
            raise ValueError("research dataset changed since session preflight")
        dataset = ParquetDataProvider.read(data)
        if (
            dataset.dataset_hash != row["dataset_hash"]
            or DataZone(dataset.zone) is not DataZone.DEVELOPMENT
        ):
            raise ValueError("research dataset identity changed")
        source = resolve_project_input(
            self.root, args.get("source_path"), ALLOWED_STRATEGY_SUFFIXES
        )
        imported = normalize_source(source)
        if imported.strategy is None:
            raise ValueError("unsupported source strategy")
        inherited_run_id = None
        inherited_semantic_hash = None
        parent_strategy = imported.strategy
        ancestor = args.get("inherit_from_generation")
        research_ancestor = args.get("research_parent_generation")
        if research_ancestor is not None and ancestor is not None:
            raise ValueError("research parent and approved parent routes are mutually exclusive")
        if research_ancestor is not None:
            if not request.get("allow_research_parent_inheritance",False):
                raise ValueError("RESEARCH_PARENT_SESSION_OPT_IN_REQUIRED")
            if type(research_ancestor) is not int or research_ancestor >= generation:
                raise ValueError("RESEARCH_PARENT_MUST_BE_PRIOR_GENERATION")
            parent_strategy,inherited_semantic_hash,inherited_run_id = (
                self._research_parent(session_id,research_ancestor,row["dataset_hash"])
            )
        if ancestor is not None:
            if not request.get("allow_verified_parent_inheritance", False):
                raise ValueError("INHERITED_PARENT_SESSION_OPT_IN_REQUIRED")
            if type(ancestor) is not int or ancestor >= generation:
                raise ValueError("INHERITED_PARENT_MUST_BE_PRIOR_GENERATION")
            parent_strategy,inherited_semantic_hash,inherited_run_id = (
                self._verified_inherited_parent(session_id,ancestor,row["dataset_hash"])
            )
        donor_strategy=None
        donor_run_id=None
        donor_semantic_hash=None
        crossover_proof=None
        execution_parent=parent_strategy
        if donor_generation is not None:
            donor_strategy,donor_semantic_hash,donor_run_id=(
                self._research_parent(session_id,donor_generation,row["dataset_hash"])
            )
            execution_parent,crossover_proof=crossover_exit(parent_strategy,donor_strategy)
            crossover_proof={
                **crossover_proof,"primary_generation":research_ancestor,
                "donor_generation":donor_generation,
                "primary_run_id":inherited_run_id,
                "donor_run_id":donor_run_id,
            }
        if not isinstance(args.get("intent"), dict):
            raise ValueError("typed ResearchIntent object required")
        intent = ResearchIntent.model_validate(args["intent"])
        if len(intent.parent_ids) != 1 or intent.parent_ids[0] != parent_strategy.strategy_id:
            raise ValueError("source parent must match typed GPT intent")
        if intent.primitive_request is not None:
            raise ValueError("unregistered primitive research is forbidden")
        features = research_feature_specs()
        apply_intent(execution_parent, intent, features)
        # Match the actual evaluator's candidate generator, seed and no-domain
        # contract exactly. Varying generation, ancestry or rationale must not
        # make an already evaluated executable strategy appear novel.
        operations = intent_to_operations(intent, features)
        proposals = generate_candidates(
            execution_parent,
            operations,
            (),
            method=request["method"],
            count=request["count"],
            seed=request["seed"] + generation - 1,
        )
        candidate_hashes = [semantic_strategy_hash(item.strategy) for item in proposals]
        previous_hashes = self._evaluated_semantic_hashes(session_id, row["dataset_hash"])
        if not candidate_hashes or len(candidate_hashes) != len(set(candidate_hashes)):
            raise ValueError("DUPLICATE_STRATEGY: proposal repeats an executable strategy")
        if previous_hashes.intersection(candidate_hashes):
            raise ValueError("DUPLICATE_STRATEGY: strategy already evaluated in this session")
        execution_hashes: tuple[str, ...] = ()
        if request.get("require_execution_change", False):
            execution_hashes = require_costed_execution_change(
                parent=parent_strategy,
                candidates=proposals,
                dataset=dataset,
            )
        # Journal exact immutable execution identity BEFORE starting the worker.
        # Any interrupted or ambiguous evaluator is never automatically replayed.
        reserved_run_id = uuid4().hex
        reserved_attempt_id = uuid4().hex
        intent_payload=intent.model_dump(mode="json",exclude_none=True)
        intent_hash = content_hash(intent_payload)
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        proposal={
            "schema":"guided-research-proposal-v1",
            "session_id":session_id,"generation":generation,
            "run_id":reserved_run_id,"dataset_hash":row["dataset_hash"],
            "parent_semantic_hash":semantic_strategy_hash(parent_strategy),
            "parent_strategy_ir":parent_strategy.model_dump(mode="json",by_alias=True),
            "parent_run_id":inherited_run_id,
            "crossover_proof":crossover_proof,
            "crossover_donor_strategy_ir":(donor_strategy.model_dump(mode="json",by_alias=True) if donor_strategy else None),
            "crossover_intermediate_ir":(execution_parent.model_dump(mode="json",by_alias=True) if donor_strategy else None),
            "parent_mode":("DEVELOPMENT_RESEARCH_ONLY" if research_ancestor is not None else
                           "POLICY_PASSED" if ancestor is not None else "EXTERNAL_SOURCE"),
            "intent":intent_payload,
            "research_director_decision":verified_decision,
            "candidates":[{
                "candidate_hash":c.candidate_hash,
                "semantic_strategy_hash":semantic_strategy_hash(c.strategy),
                "strategy_ir":c.strategy.model_dump(mode="json",by_alias=True),
                "strategy_ir_hash":content_hash(c.strategy.model_dump(mode="json",by_alias=True)),
            } for c in proposals],
            "independent_oos_approved":False,"orders_enabled":False,
        }
        proposal_hash=content_hash(proposal)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for execution_hash in execution_hashes:
                existing = db.execute(
                    "SELECT session_id,generation FROM guided_execution_signatures "
                    "WHERE dataset_hash=? AND execution_hash=?",
                    (row["dataset_hash"], execution_hash),
                ).fetchone()
                if existing:
                    raise ValueError(
                        "DUPLICATE_EXECUTION_TRACE: previously reserved or evaluated "
                        f"in {existing['session_id']} generation {existing['generation']}"
                    )
            cur = db.execute(
                "UPDATE sessions SET status='EXECUTING',token=NULL,"
                "inflight_run_id=?, inflight_attempt_id=?, inflight_intent_hash=?,"
                "inflight_semantic_hashes_json=?, inflight_source_sha256=?, "
                "inflight_execution_hashes_json=?, inflight_parent_run_id=?, "
                "inflight_parent_semantic_hash=?, inflight_proposal_hash=?, "
                "inflight_donor_run_id=?, inflight_donor_semantic_hash=? "
                "WHERE id=? AND status='AWAITING_GPT' AND completed=? AND token=?",
                (
                    reserved_run_id,
                    reserved_attempt_id,
                    intent_hash,
                    json.dumps(sorted(candidate_hashes)),
                    source_hash,
                    json.dumps(list(execution_hashes)),
                    inherited_run_id,
                    inherited_semantic_hash,
                    proposal_hash,
                    donor_run_id,
                    donor_semantic_hash,
                    session_id,
                    generation - 1,
                    token,
                ),
            )
            if cur.rowcount != 1:
                raise ValueError("stale checkpoint concurrently claimed")
            db.execute(
                "INSERT INTO guided_research_proposals "
                "(run_id,session_id,generation,proposal_json,proposal_hash,status) "
                "VALUES(?,?,?,?,?,'RESERVED')",
                (reserved_run_id,session_id,generation,
                 json.dumps(proposal,sort_keys=True),proposal_hash),
            )
            for execution_hash in execution_hashes:
                db.execute(
                    "INSERT INTO guided_execution_signatures "
                    "(dataset_hash, execution_hash, session_id, generation, run_id, status) "
                    "VALUES (?,?,?,?,?,'RESERVED')",
                    (row["dataset_hash"], execution_hash, session_id,
                     generation, reserved_run_id),
                )
        try:
            executor = ChatDirectedResearchService(
                project_root=self.root,
                state_dir=self.state_dir,
                evaluation=EvaluationService(project_root=self.root, state_dir=self.state_dir),
            )
            result = executor.run(
                source_path=source.relative_to(self.root).as_posix(),
                data_path=request["data_path"],
                intent_payload=intent.model_dump(mode="json", exclude_none=True),
                method=request["method"],
                count=request["count"],
                seed=request["seed"] + generation - 1,
                min_trades=request["min_trades"],
                min_annual_trades=request["min_annual_trades"],
                min_qqq_cagr_delta=request["min_qqq_cagr_delta"],
                benchmark_mode=request.get("benchmark_mode"),
                previous_research_run_id=row["previous_run_id"],
                guided_session_id=session_id,
                guided_generation=generation,
                reserved_run_id=reserved_run_id,
                reserved_attempt_id=reserved_attempt_id,
                expected_semantic_hashes=tuple(sorted(candidate_hashes)),
                source_sha256=source_hash,
                parent_override=parent_strategy if inherited_run_id is not None else None,
                inherited_parent_run_id=inherited_run_id,
                inherited_parent_semantic_hash=inherited_semantic_hash,
                guided_proposal_hash=proposal_hash,
                crossover_donor=donor_strategy,
                crossover_donor_run_id=donor_run_id,
            )
            if (
                result.get("research_run_id") != reserved_run_id
                or result.get("attempt_id") != reserved_attempt_id
            ):
                raise ValueError("evaluator returned unexpected reserved Evidence identity")
            committed=self._finalize_inflight(session_id)
            if request.get("allow_research_parent_inheritance",False):
                # A committed evaluator is never replayed on control failure.
                # The operator can explicitly regenerate/read the separate
                # training-only control, never changing the existing checkpoint.
                self._record_training_control(session_id,generation)
                return self.get(session_id)
            return committed
        except Exception:
            # Do not silently rerun an evaluator that might have committed Evidence.
            with self._connect() as db:
                db.execute(
                    "UPDATE sessions SET status='INTERRUPTED' WHERE id=? AND status='EXECUTING'",
                    (session_id,),
                )
            raise
