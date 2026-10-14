"""S4 checkpointed, external-LLM-directed academic research cycles.

A generation is complete ONLY after algorithm design, canonical development
backtest, trace capture and evidence-bound LLM diagnostic planning all succeed.
No embedded model transport, hidden retries, live orders or sealed OOS access.
External authenticated ChatGPT/MCP must supply the actual model transport.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from core.data.contracts import DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.algorithm_plan import (
    AlgorithmPlanProvider,
    audit_algorithm_plan,
    compile_provider_algorithm_plan,
)
from research.indicator_engine.catalog import ResearchCatalog
from research.llm.diagnostic_research import diagnose_with_provider


class CycleStateError(ValueError):
    """Invalid research checkpoint, provider state or immutable evidence."""


class CycleResearcher(AlgorithmPlanProvider, Protocol):
    """Approved *external* GPT transport; two structured proposals per generation."""


class _GenerationPlanProvider:
    def __init__(
        self, delegate: CycleResearcher, generation: int,
        prior: dict[str, Any] | None,
    ) -> None:
        self.delegate = delegate
        self.generation = generation
        self.prior = prior

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        context = deepcopy(context)
        context["generation"] = self.generation
        if self.prior is not None:
            context["prior_research"] = {
                "generation": self.prior["generation"],
                "evidence_hash": self.prior["evidence_hash"],
                "audit_hash": self.prior["audit_hash"],
                "diagnostic_proposal_hash": self.prior["diagnostic_proposal_hash"],
                "causal_status": self.prior["causal_status"],
                "analysis_summary": self.prior["analysis_summary"],
                "experiments": self.prior["experiments"],
                "metrics": self.prior["metrics"],
                "prior_algorithm_semantic_hash": self.prior["algorithm_semantic_hash"],
            }
        response = self.delegate.propose(context)
        if not isinstance(response, dict):
            raise CycleStateError("model must return a structured plan")
        return response


class AcademicCycleService:
    """Durable one-generation-at-a-time controller for verified development data.

    SQLite is a local append-only **logical** evidence ledger, not a signed
    witness; its checksum catches accidental corruption, not malicious rehash.
    During provider execution the session is EXECUTING (single claimant).
    After a crash it needs explicit operator reconciliation before retry.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                requested INTEGER NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                dataset_hash TEXT NOT NULL,
                catalog_hash TEXT NOT NULL,
                running_token TEXT,
                error_type TEXT
            );
            CREATE TABLE IF NOT EXISTS generations (
                session_id TEXT NOT NULL REFERENCES sessions(id),
                generation INTEGER NOT NULL,
                evidence_json TEXT NOT NULL,
                evidence_hash TEXT NOT NULL,
                PRIMARY KEY(session_id, generation)
            );
        """)
        return db

    @staticmethod
    def _check_market(market: MarketDataSet) -> None:
        if market.zone != DataZone.DEVELOPMENT:
            raise CycleStateError("only development research data is allowed")
        if (
            market.calendar != "us_equities" or market.timeframe != "1d"
            or not 2 <= len(market.bars) <= 1_000_000
            or len({bar.symbol for bar in market.bars}) != 1
        ):
            raise CycleStateError("unsupported academic single-asset dataset")

    @staticmethod
    def _catalog_hash(catalog: ResearchCatalog) -> str:
        return content_hash(tuple(
            indicator.model_dump(mode="json")
            for indicator in catalog.list_indicators()
        ))

    def _validate_dataset(
        self, row: sqlite3.Row,
        catalog: ResearchCatalog,
        market: MarketDataSet,
    ) -> None:
        if (market.dataset_hash != row["dataset_hash"]
                or market.zone != DataZone.DEVELOPMENT):
            raise CycleStateError("research dataset identity mismatch")
        if self._catalog_hash(catalog) != row["catalog_hash"]:
            raise CycleStateError("research indicator catalog identity mismatch")

    @staticmethod
    def _row_evidence_hash(
        session_id: str, generation: int,
        previous_hash: str | None, payload: dict[str, Any],
    ) -> str:
        return content_hash({
            "schema": "external-gpt-academic-generation-v1",
            "session_id": session_id,
            "generation": generation,
            "previous_hash": previous_hash,
            "payload": payload,
        })

    def _history(self, db: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
        rows = db.execute(
            "SELECT generation,evidence_json,evidence_hash FROM generations "
            "WHERE session_id=? ORDER BY generation", (session_id,),
        ).fetchall()
        history: list[dict[str, Any]] = []
        predecessor: str | None = None
        for expected, row in enumerate(rows, start=1):
            try:
                payload = json.loads(row["evidence_json"])
            except (ValueError, TypeError) as exc:
                raise CycleStateError("evidence integrity: malformed checkpoint") from exc
            if (
                row["generation"] != expected
                or not isinstance(payload, dict)
                or payload.get("generation") != expected
                or payload.get("previous_evidence_hash") != predecessor
                or row["evidence_hash"] != self._row_evidence_hash(
                    session_id, expected, predecessor, payload
                )
            ):
                raise CycleStateError("evidence integrity: broken generation hash chain")
            current = {**payload, "evidence_hash": str(row["evidence_hash"])}
            history.append(current)
            predecessor = str(row["evidence_hash"])
        return history

    def start(
        self, catalog: ResearchCatalog, market: MarketDataSet,
        *, generations: int,
    ) -> dict[str, Any]:
        self._check_market(market)
        if type(generations) is not int or not 1 <= generations <= 100:
            raise CycleStateError("generations must be an integer 1-100")
        session_id = uuid4().hex
        with self._connect() as db:
            db.execute(
                "INSERT INTO sessions"
                "(id,requested,completed,status,dataset_hash,catalog_hash) "
                "VALUES(?,?,0,'AWAITING_PROVIDER',?,?)",
                (session_id, generations, market.dataset_hash, self._catalog_hash(catalog)),
            )
        return self.get(session_id, catalog, market)

    def get(
        self, session_id: str, catalog: ResearchCatalog,
        market: MarketDataSet,
    ) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise CycleStateError("unknown academic research session")
            self._validate_dataset(row, catalog, market)
            history = self._history(db, session_id)
            if (
                len(history) != row["completed"]
                or row["completed"] > row["requested"]
                or (row["status"] == "COMPLETED"
                    and row["completed"] != row["requested"])
            ):
                raise CycleStateError("evidence integrity: session counter mismatch")
            return {
                "session_id": session_id,
                "status": row["status"],
                "requested_generations": row["requested"],
                "completed_generations": row["completed"],
                "dataset_hash": row["dataset_hash"],
                "history": history,
                "error_type": row["error_type"],
                "orders_enabled": False,
                "independent_oos_approved": False,
                "real_model_connection_verified": False,
                "scope": "NON_PIT_DEVELOPMENT_EXTERNAL_GPT_CHECKPOINTS",
            }

    def resume(
        self, session_id: str, catalog: ResearchCatalog, market: MarketDataSet,
    ) -> dict[str, Any]:
        state = self.get(session_id, catalog, market)
        if state["status"] != "INTERRUPTED":
            raise CycleStateError("only interrupted research may explicitly resume")
        with self._connect() as db:
            db.execute(
                "UPDATE sessions SET status='AWAITING_PROVIDER', error_type=NULL "
                "WHERE id=? AND status='INTERRUPTED'", (session_id,),
            )
        return self.get(session_id, catalog, market)

    def advance(
        self, session_id: str, catalog: ResearchCatalog,
        market: MarketDataSet, provider: CycleResearcher | None,
    ) -> dict[str, Any]:
        state = self.get(session_id, catalog, market)
        if state["status"] == "COMPLETED":
            raise CycleStateError("research session already complete")
        if state["status"] != "AWAITING_PROVIDER":
            raise CycleStateError("research interrupted or executing; explicitly resume")
        if provider is None:
            raise CycleStateError("external GPT provider is required")
        generation = int(state["completed_generations"]) + 1
        history: list[dict[str, Any]] = state["history"]
        prior = history[-1] if history else None
        token = uuid4().hex
        with self._connect() as db:
            result = db.execute(
                "UPDATE sessions SET status='EXECUTING',running_token=? "
                "WHERE id=? AND status='AWAITING_PROVIDER' AND completed=?",
                (token, session_id, generation - 1),
            )
            if result.rowcount != 1:
                raise CycleStateError("concurrent session claim denied")
        try:
            return self._execute_claimed(
                session_id, generation, catalog, market, provider, prior, history, token
            )
        except Exception as exc:
            with self._connect() as db:
                db.execute(
                    "UPDATE sessions SET status='INTERRUPTED', running_token=NULL,"
                    "error_type=? WHERE id=? AND running_token=? AND status='EXECUTING'",
                    (type(exc).__name__, session_id, token),
                )
            raise

    def _execute_claimed(
        self, session_id: str, generation: int, catalog: ResearchCatalog,
        market: MarketDataSet, provider: CycleResearcher,
        prior: dict[str, Any] | None, history: list[dict[str, Any]], token: str,
    ) -> dict[str, Any]:
        wrapped = _GenerationPlanProvider(provider, generation, prior)
        compiled = compile_provider_algorithm_plan(catalog, wrapped, market)
        plan = compiled.plan
        semantic_hash = content_hash(plan.model_dump(mode="json", exclude={"plan_id"}))
        if any(h["algorithm_semantic_hash"] == semantic_hash for h in history):
            raise CycleStateError("duplicate algorithm logic cannot become a new generation")
        # Parameter edits may be semantically distinct yet produce identical
        # actual entry/hold actions on the same frozen development data.
        # Distinguish algorithm novelty from observed effective-signal novelty.
        vectors = compiled.compiled.feature_values
        behavioral_hash = content_hash({
            "dataset_hash": market.dataset_hash,
            "entry": vectors["plan_entry"],
            "regime": vectors["plan_regime"],
        })
        if any(h["effective_signal_hash"] == behavioral_hash for h in history):
            raise CycleStateError("duplicate effective signals on frozen development data")
        audit = audit_algorithm_plan(catalog, compiled, market)
        # Existing S2 gate independently rehashes measured audit evidence.
        diagnosis = diagnose_with_provider(audit, compiled.compiled.strategy, provider)
        payload: dict[str, Any] = {
            "generation": generation,
            "previous_evidence_hash": prior["evidence_hash"] if prior else None,
            "algorithm_plan": plan.model_dump(mode="json"),
            "algorithm_semantic_hash": semantic_hash,
            "effective_signal_hash": behavioral_hash,
            "plan_hash": compiled.plan_hash,
            "strategy_hash": compiled.compiled.strategy_hash,
            "audit_hash": audit.trace_hash,
            "diagnostic_context_hash": diagnosis.context_hash,
            "diagnostic_proposal_hash": diagnosis.proposal_hash,
            "analysis_summary": diagnosis.analysis_summary,
            "causal_status": diagnosis.causal_claim,
            "hypothesis_ids": [x.hypothesis_id for x in diagnosis.experiments],
            "experiments": [
                {
                    "hypothesis_id": x.hypothesis_id,
                    "observed_ids": list(x.observed_ids),
                    "mechanism": x.mechanism,
                    "alternative": x.alternative,
                    "test_design": x.test_design,
                    "control": x.control,
                    "expected_metric": x.expected_metric,
                    "predicted_direction": x.predicted_direction,
                    "proposal_child_hash": x.child_hash,
                    "proposed_intent": x.proposed_intent.model_dump(mode="json"),
                    "status": x.causal_status,
                }
                for x in diagnosis.experiments
            ],
            "observed_trades": audit.evaluation.trades_count,
            "metrics": audit.llm_packet["metrics"],
            "measured_final_equity": audit.evaluation.final_equity,
            "dataset_hash": market.dataset_hash,
            "independent_oos_approved": False,
            "broker_executable": False,
        }
        digest = self._row_evidence_hash(
            session_id, generation, prior["evidence_hash"] if prior else None, payload
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if (
                row is None or row["status"] != "EXECUTING"
                or row["running_token"] != token
                or row["completed"] != generation - 1
            ):
                raise CycleStateError("generation checkpoint ownership conflict")
            self._validate_dataset(row, catalog, market)
            self._history(db, session_id)  # Reject corrupted prior Evidence before committing.
            db.execute(
                "INSERT INTO generations(session_id,generation,evidence_json,evidence_hash) "
                "VALUES(?,?,?,?)",
                (session_id, generation, json.dumps(payload, sort_keys=True), digest),
            )
            db.execute(
                "UPDATE sessions SET completed=?, status=?, running_token=NULL, "
                "error_type=NULL WHERE id=? AND running_token=?",
                (
                    generation,
                    "COMPLETED" if generation == row["requested"] else "AWAITING_PROVIDER",
                    session_id, token,
                ),
            )
        return self.get(session_id, catalog, market)


    def run_bounded(
        self, session_id: str, catalog: ResearchCatalog,
        market: MarketDataSet, provider: CycleResearcher | None,
        *, max_steps: int,
    ) -> dict[str, Any]:
        """Run up to N complete cycles without between-generation user prompts.

        This cannot run unattended without a real external model transport.
        It never starts a background worker; the caller owns the lifetime.
        """
        if type(max_steps) is not int or not 1 <= max_steps <= 100:
            raise CycleStateError("max_steps must be an integer 1-100")
        state = self.get(session_id, catalog, market)
        for _ in range(max_steps):
            if state["status"] == "COMPLETED":
                break
            state = self.advance(session_id, catalog, market, provider)
        return state
