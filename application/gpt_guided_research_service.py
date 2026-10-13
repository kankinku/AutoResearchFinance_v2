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
from experiments.candidate_generator import generate_candidates
from experiments.identity import semantic_strategy_hash
from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from orchestration.evaluation_runner import (
    ALLOWED_STRATEGY_SUFFIXES,
    resolve_project_input,
)
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent, intent_to_operations
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
        """)
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
        request = {
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
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,0,?,NULL)",
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
        return {
            "session_id": session_id,
            "status": row["status"],
            "requested_generations": row["requested"],
            "completed_generations": row["completed"],
            "generation": row["completed"] + 1 if waiting else None,
            "checkpoint_token": row["token"] if waiting else None,
            "last_run_id": row["previous_run_id"],
            "previous_failed_gates": history[-1]["failed_gates"] if history else [],
            "previous_evaluated_strategies": len(previously_evaluated),
            "previous_semantic_strategy_hashes": sorted(previously_evaluated),
            "research_inputs": {
                "data_path": request["data_path"],
                "method": request["method"],
                "count": request["count"],
            },
            "next_action": "GPT_SUBMIT_TYPED_INTENT" if waiting else "NONE",
            "history": history,
            "orders_enabled": False,
            "sealed_oos_evaluated": False,
            "validation_scope": "REUSED_DEVELOPMENT_DATA_NOT_INDEPENDENT_OOS",
            "llm_controller": "external_mcp_client_each_generation",
        }

    def submit(self, args: dict[str, Any]) -> dict[str, object]:
        allowed = {"session_id", "checkpoint_token", "generation", "source_path", "intent"}
        if set(args) - allowed:
            raise ValueError("guided generation cannot override fixed evaluation gates or dataset")
        session_id = args.get("session_id")
        if not isinstance(session_id, str):
            raise ValueError("guided session ID is required")
        row, request = self._read(session_id)
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
        if not isinstance(args.get("intent"), dict):
            raise ValueError("typed ResearchIntent object required")
        intent = ResearchIntent.model_validate(args["intent"])
        if len(intent.parent_ids) != 1 or intent.parent_ids[0] != imported.strategy.strategy_id:
            raise ValueError("source parent must match typed GPT intent")
        if intent.primitive_request is not None:
            raise ValueError("unregistered primitive research is forbidden")
        features = research_feature_specs()
        apply_intent(imported.strategy, intent, features)
        # Match the actual evaluator's candidate generator, seed and no-domain
        # contract exactly. Varying generation, ancestry or rationale must not
        # make an already evaluated executable strategy appear novel.
        operations = intent_to_operations(intent, features)
        proposals = generate_candidates(
            imported.strategy,
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
        # This single compare-and-swap authorizes one evaluator invocation.
        # A crashed/ambiguous invocation is INTERRUPTED, never automatically replayed.
        with self._connect() as db:
            cur = db.execute(
                "UPDATE sessions SET status='EXECUTING',token=NULL "
                "WHERE id=? AND status='AWAITING_GPT' AND completed=? AND token=?",
                (session_id, generation - 1, token),
            )
            if cur.rowcount != 1:
                raise ValueError("stale checkpoint concurrently claimed")
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
                previous_research_run_id=row["previous_run_id"],
            )
            run_id = result.get("research_run_id")
            attempt_id = result.get("attempt_id")
            if not isinstance(run_id, str) or not isinstance(attempt_id, str):
                raise ValueError("evaluator did not return auditable research identity")
            evidence = EvidenceStore(self.state_dir).events()
            matches = [
                event["payload"]
                for event in evidence
                if event["kind"] == "attempt"
                and event["payload"].get("research_run_id") == run_id
                and event["payload"].get("attempt_id") == attempt_id
            ]
            if (
                len(matches) != 1
                or matches[0]["status"] != "COMPLETED"
                or matches[0].get("verification") is not None
            ):
                raise ValueError("guided evaluation lacks verified immutable attempt evidence")
            candidate_rows = matches[0]["candidates"]
            if not candidate_rows or any(
                c.get("dataset_hash") != row["dataset_hash"] for c in candidate_rows
            ):
                raise ValueError("guided evaluation is missing comparable candidate evidence")
            failed_gates = sorted(
                {gate for c in candidate_rows for gate in c.get("failed_gates", [])}
            )
            final = generation == row["requested"]
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO steps VALUES(?,?,?,?,?,?)",
                    (
                        session_id,
                        generation,
                        run_id,
                        attempt_id,
                        row["previous_run_id"],
                        json.dumps(failed_gates, sort_keys=True),
                    ),
                )
                updated = db.execute(
                    "UPDATE sessions SET completed=?, status=?, token=?, previous_run_id=? "
                    "WHERE id=? AND status='EXECUTING' AND completed=?",
                    (
                        generation,
                        "COMPLETED" if final else "AWAITING_GPT",
                        None if final else secrets.token_hex(16),
                        run_id,
                        session_id,
                        generation - 1,
                    ),
                )
                if updated.rowcount != 1:
                    raise ValueError("guided session checkpoint journal conflict")
            return self.get(session_id)
        except Exception:
            # Do not silently rerun an evaluator that might have committed Evidence.
            with self._connect() as db:
                db.execute(
                    "UPDATE sessions SET status='INTERRUPTED' WHERE id=? AND status='EXECUTING'",
                    (session_id,),
                )
            raise
