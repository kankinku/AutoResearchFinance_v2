"""Durable GPT-directed, bounded batch research and measured per-generation ETA.

No LLM process is used by the batch executor. GPT provides the validated plan
once; deterministic local evaluation chooses only audited eligible successors.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, cast
from uuid import uuid4

from application.evaluation_service import EvaluationService
from core.features.registry import research_feature_specs
from memory.evidence_store import EvidenceIntegrityError
from orchestration.evaluation_runner import ALLOWED_STRATEGY_SUFFIXES, resolve_project_input
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent, intent_to_operations
from runtime.evidence_session import EvidenceSession
from runtime.process_lifecycle import process_matches
from runtime.research_loop import _strategy_from_evaluation
from strategy_ir.normalizer import normalize_source

MAX_GENERATIONS = 100
MAX_CANDIDATES = 64


class BatchRequestError(ValueError):
    """A safe, user-actionable research preflight failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"})


def _timestamp(value: float | None) -> str | None:
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


def _bounded_int(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


class ResearchBatchService:
    """Run across MCP requests with SQLite journal and a detached local worker."""

    def __init__(self, *, project_root: Path, state_dir: Path) -> None:
        self.project_root = project_root.resolve()
        self.state_dir = state_dir.resolve()
        self.database = self.state_dir / "system" / "gpt-research-batches.sqlite"

    def _connect(self) -> sqlite3.Connection:
        self.database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, request_json TEXT NOT NULL,
                requested INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0,
                created REAL NOT NULL, started REAL, finished REAL,
                pid INTEGER, heartbeat REAL, cancel INTEGER NOT NULL DEFAULT 0,
                research_run_id TEXT, error_code TEXT
            );
            CREATE TABLE IF NOT EXISTS generation_history (
                batch_id TEXT NOT NULL, generation INTEGER NOT NULL, seconds REAL NOT NULL,
                method TEXT NOT NULL, count INTEGER NOT NULL, parent_id TEXT NOT NULL,
                successor_id TEXT NOT NULL, result_status TEXT NOT NULL,
                result_counts TEXT NOT NULL, candidate_count INTEGER NOT NULL,
                PRIMARY KEY(batch_id, generation)
            );
        """)
        return db

    def _validate_request(self, args: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "source_path",
            "data_path",
            "intent",
            "generations",
            "count",
            "method",
            "seed",
            "min_trades",
            "min_annual_trades",
            "min_qqq_cagr_delta",
            "series_data_path",
        }
        if set(args) - allowed:
            raise ValueError("unexpected batch arguments")
        source = args.get("source_path")
        data = args.get("data_path")
        if not isinstance(source, str) or not isinstance(data, str):
            raise ValueError("source_path and data_path are required")
        try:
            source_abs = resolve_project_input(self.project_root, source, ALLOWED_STRATEGY_SUFFIXES)
        except FileNotFoundError as exc:
            raise BatchRequestError(
                "SOURCE_FILE_NOT_FOUND",
                "source_path must refer to an existing strategy file. "
                "Read get_research_brief.research_inputs for known paths.",
            ) from exc
        try:
            data_abs = resolve_project_input(self.project_root, data, frozenset({".parquet"}))
        except FileNotFoundError as exc:
            raise BatchRequestError(
                "DATA_FILE_NOT_FOUND",
                "data_path must refer to an existing Parquet file inside this project. "
                "No research was queued. Check get_research_brief.research_inputs.",
            ) from exc
        series = args.get("series_data_path")
        if series is not None and not isinstance(series, str):
            raise ValueError("series_data_path must be a string")
        series_abs = (
            resolve_project_input(self.project_root, series, frozenset({".parquet"}))
            if series is not None
            else None
        )
        imported = normalize_source(source_abs)
        if imported.strategy is None:
            raise ValueError("unsupported strategy source")
        if not isinstance(args.get("intent"), dict):
            raise ValueError("GPT must provide a structured ResearchIntent")
        intent = ResearchIntent.model_validate(args["intent"])
        if len(intent.parent_ids) != 1 or intent.parent_ids[0] != imported.strategy.strategy_id:
            raise BatchRequestError(
                "PARENT_ID_MISMATCH",
                "intent.parent_ids must contain exactly one ID, matching the "
                "strategy_id reported for source_path in get_research_brief.research_inputs.",
            )
        if intent.primitive_request is not None:
            raise ValueError("unregistered primitive requests cannot be executed")
        feature_specs = research_feature_specs()
        intent_to_operations(intent, feature_specs)
        apply_intent(imported.strategy, intent, feature_specs)
        generations = _bounded_int(args.get("generations"), "generations", 1, MAX_GENERATIONS)
        count = _bounded_int(args.get("count", 8), "count", 1, MAX_CANDIDATES)
        seed = _bounded_int(args.get("seed", 0), "seed", 0, 2**31 - 1 - MAX_GENERATIONS)
        min_trades = _bounded_int(args.get("min_trades", 10), "min_trades", 0, 100000)
        min_annual = _bounded_int(args.get("min_annual_trades", 30), "min_annual_trades", 0, 100000)
        method = args.get("method", "random")
        if method not in ("grid", "random", "bayesian"):
            raise ValueError("invalid search method")
        delta = args.get("min_qqq_cagr_delta")
        if delta is not None:
            if (
                isinstance(delta, bool)
                or not isinstance(delta, (float, int))
                or not math.isfinite(delta)
            ):
                raise ValueError("min_qqq_cagr_delta must be finite")
            delta = float(delta)
        return {
            "source_path": source_abs.relative_to(self.project_root).as_posix(),
            "data_path": data_abs.relative_to(self.project_root).as_posix(),
            "series_data_path": (
                series_abs.relative_to(self.project_root).as_posix() if series_abs else None
            ),
            "intent": intent.model_dump(mode="json", exclude_none=True),
            "generations": generations,
            "count": count,
            "method": method,
            "seed": seed,
            "min_trades": min_trades,
            "min_annual_trades": min_annual,
            "min_qqq_cagr_delta": delta,
        }

    def describe_inputs(self) -> dict[str, object]:
        """Bounded, project-local input discovery; never invent market data."""
        sources: list[dict[str, str]] = []
        directory = self.project_root / "strategies" / "normalized"
        for path in sorted(directory.glob("*.json"))[:100]:
            try:
                validated = resolve_project_input(
                    self.project_root,
                    path.relative_to(self.project_root).as_posix(),
                    ALLOWED_STRATEGY_SUFFIXES,
                )
                result = normalize_source(validated)
                if result.strategy is not None:
                    sources.append(
                        {
                            "source_path": validated.relative_to(self.project_root).as_posix(),
                            "strategy_id": result.strategy.strategy_id,
                        }
                    )
            except (OSError, ValueError, PermissionError):
                continue
        datasets: list[str] = []
        candidates = list(self.project_root.glob("*.parquet"))
        for dirname in ("data", "datasets"):
            candidates.extend((self.project_root / dirname).rglob("*.parquet"))
        for path in sorted(set(candidates))[:200]:
            try:
                checked = resolve_project_input(
                    self.project_root,
                    path.relative_to(self.project_root).as_posix(),
                    frozenset({".parquet"}),
                )
                datasets.append(checked.relative_to(self.project_root).as_posix())
            except (OSError, ValueError, PermissionError):
                continue
        return {
            "sources": sources,
            "data_paths": datasets,
            "ready_for_batch": bool(sources and datasets),
            "note": (
                "Choose an exact source_path and its strategy_id from sources. "
                "Use an existing Parquet data_path; do not create or guess paths."
            ),
        }

    def start(self, args: dict[str, Any]) -> dict[str, object]:
        request = self._validate_request(args)
        # Reconcile workers terminated by host restart before enforcing concurrency.
        with self._connect() as scan:
            active_ids = [
                r["id"]
                for r in scan.execute(
                    "SELECT id FROM batches WHERE status IN ('QUEUED','RUNNING')"
                ).fetchall()
            ]
        for active_id in active_ids:
            self._job(str(active_id))
        now = time.time()
        job_id = uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # One detached research worker at a time. Avoid accidental CPU/GPU contention.
            running = db.execute(
                "SELECT id FROM batches WHERE status IN ('QUEUED','RUNNING') LIMIT 1"
            ).fetchone()
            if running is not None:
                raise ValueError("another research batch is already active")
            db.execute(
                "INSERT INTO batches(id,status,request_json,requested,created) VALUES(?,?,?,?,?)",
                (job_id, "QUEUED", json.dumps(request), request["generations"], now),
            )
        try:
            worker = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "application.research_batch_worker",
                    "--project-root",
                    str(self.project_root),
                    "--state-dir",
                    str(self.state_dir),
                    "--job-id",
                    job_id,
                ],
                cwd=self.project_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
            )
        except OSError:
            with self._connect() as db:
                db.execute(
                    (
                        "UPDATE batches SET status='FAILED',finished=?,"
                        "error_code='WORKER_START_FAILED' WHERE id=?"
                    ),
                    (time.time(), job_id),
                )
            raise
        with self._connect() as db:
            db.execute(
                "UPDATE batches SET pid=? WHERE id=? AND status='QUEUED'", (worker.pid, job_id)
            )
        return self.status(job_id)

    def _job(self, job_id: str | None) -> sqlite3.Row:
        with self._connect() as db:
            row = (
                db.execute("SELECT * FROM batches ORDER BY created DESC LIMIT 1").fetchone()
                if job_id is None
                else db.execute("SELECT * FROM batches WHERE id=?", (job_id,)).fetchone()
            )
        if row is None:
            raise ValueError("research batch not found")
        # A killed worker must not show RUNNING forever after a host restart.
        if row["status"] in {"QUEUED", "RUNNING"}:
            pid = row["pid"]
            expired_startup = time.time() - float(row["created"]) > 10
            if (
                pid is not None
                and (row["status"] == "RUNNING" or expired_startup)
                and not process_matches(
                    int(pid),
                    ("application.research_batch_worker", str(row["id"])),
                    startup_retries=0,
                )
            ) or (pid is None and expired_startup):
                with self._connect() as db:
                    db.execute(
                        "UPDATE batches SET status='INTERRUPTED',finished=?, "
                        "error_code='WORKER_GONE' "
                        "WHERE id=? AND status IN ('QUEUED','RUNNING')",
                        (time.time(), row["id"]),
                    )
                    row = db.execute("SELECT * FROM batches WHERE id=?", (row["id"],)).fetchone()
        return cast(sqlite3.Row, row)

    def _estimate(
        self, db: sqlite3.Connection, method: str, count: int
    ) -> tuple[float | None, int]:
        rows = db.execute(
            (
                "SELECT seconds,count FROM generation_history WHERE method=? AND seconds>0 "
                "ORDER BY rowid DESC LIMIT 40"
            ),
            (method,),
        ).fetchall()
        if not rows:
            return None, 0
        # Normalize to comparable candidate budget and use median against outliers.
        values = [float(r["seconds"]) * count / int(r["count"]) for r in rows]
        return round(median(values), 3), len(rows)

    def status(self, job_id: str | None = None) -> dict[str, object]:
        row = self._job(job_id)
        request = json.loads(row["request_json"])
        with self._connect() as db:
            durations = db.execute(
                "SELECT seconds FROM generation_history WHERE batch_id=? ORDER BY generation",
                (row["id"],),
            ).fetchall()
            historical, samples = self._estimate(db, request["method"], request["count"])
        own = [float(i["seconds"]) for i in durations if float(i["seconds"]) > 0]
        basis = round(median(own[-7:]), 3) if own else historical
        remaining = row["requested"] - row["completed"]
        eta_seconds = (
            round(basis * remaining, 1)
            if basis is not None and row["status"] not in _TERMINAL
            else None
        )
        # If no samples, do NOT invent an ETA.
        return {
            "job_id": row["id"],
            "status": row["status"],
            "requested_generations": row["requested"],
            "completed_generations": row["completed"],
            "progress_percent": round(100 * row["completed"] / row["requested"], 1),
            "started_at_utc": _timestamp(row["started"]),
            "created_at_utc": _timestamp(row["created"]),
            "finished_at_utc": _timestamp(row["finished"]),
            "average_generation_seconds": round(sum(own) / len(own), 3) if own else None,
            "estimated_seconds_per_generation": basis,
            "eta_seconds": eta_seconds,
            "estimated_finish_utc": _timestamp(time.time() + eta_seconds)
            if eta_seconds is not None
            else None,
            "eta_basis": "current_batch"
            if own
            else ("historical" if historical is not None else "insufficient_data"),
            "historical_samples": samples,
            "research_run_id": row["research_run_id"],
            "error_code": row["error_code"],
            "orders_enabled": False,
            "research_controller": "external_gpt_plan_local_deterministic_worker",
        }

    def cancel(self, job_id: str | None = None) -> dict[str, object]:
        row = self._job(job_id)
        with self._connect() as db:
            db.execute(
                "UPDATE batches SET cancel=1 WHERE id=? AND status IN ('QUEUED','RUNNING')",
                (row["id"],),
            )
        return {**self.status(row["id"]), "cancel_requested": True}

    def report(self, job_id: str | None = None) -> dict[str, object]:
        status = self.status(job_id)
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM generation_history WHERE batch_id=? ORDER BY generation",
                (status["job_id"],),
            ).fetchall()
        generations = [
            {
                "generation": r["generation"],
                "duration_seconds": round(r["seconds"], 3),
                "parent_id": r["parent_id"],
                "successor_id": r["successor_id"],
                "status": r["result_status"],
                "candidate_count": r["candidate_count"],
                "counts": json.loads(r["result_counts"]),
            }
            for r in rows
        ]
        return {
            **status,
            "generations": generations,
            "total_measured_seconds": round(sum(float(r["seconds"]) for r in rows), 3),
            "final_report_ready": status["status"] in _TERMINAL,
            "oos_approved": False,
        }

    def execute(self, job_id: str) -> None:
        row = self._job(job_id)
        request = json.loads(row["request_json"])
        with self._connect() as db:
            cur = db.execute(
                (
                    "UPDATE batches SET status='RUNNING',started=?,heartbeat=?,pid=? "
                    "WHERE id=? AND status='QUEUED'"
                ),
                (time.time(), time.time(), os.getpid(), job_id),
            )
            if cur.rowcount != 1:
                return
        evidence: EvidenceSession | None = None
        try:
            strategy = normalize_source(self.project_root / request["source_path"]).strategy
            if strategy is None:
                raise ValueError("source strategy changed or is invalid")
            intent = ResearchIntent.model_validate(request["intent"])
            specs = research_feature_specs()
            operations = intent_to_operations(intent, specs)
            apply_intent(strategy, intent, specs)
            evidence = EvidenceSession(
                self.state_dir,
                requested_generations=request["generations"],
                seed=request["seed"],
                settings={
                    "controller": "external_gpt_batch",
                    "job_id": job_id,
                    "fixed_research_intent": True,
                    "orders_enabled": False,
                },
            )
            with self._connect() as db:
                db.execute(
                    "UPDATE batches SET research_run_id=? WHERE id=?", (evidence.run_id, job_id)
                )
            evaluator = EvaluationService(project_root=self.project_root, state_dir=self.state_dir)
            for number in range(1, request["generations"] + 1):
                with self._connect() as db:
                    cancel = db.execute(
                        "SELECT cancel FROM batches WHERE id=?", (job_id,)
                    ).fetchone()[0]
                if cancel:
                    evidence.finish_run("CANCELLED")
                    with self._connect() as db:
                        db.execute(
                            "UPDATE batches SET status='CANCELLED',finished=? WHERE id=?",
                            (time.time(), job_id),
                        )
                    return
                began = time.monotonic()
                parent_id = strategy.strategy_id
                # Successor is adopted ONLY from auditable eligible immutable Evidence.
                result = evidence.evaluate(
                    evaluator.run,
                    source_path=request["source_path"],
                    data_path=request["data_path"],
                    series_data_path=request["series_data_path"],
                    method=request["method"],
                    count=request["count"],
                    seed=request["seed"] + number - 1,
                    generation=number,
                    min_trades=request["min_trades"],
                    min_annual_trades=request["min_annual_trades"],
                    min_qqq_cagr_delta=request["min_qqq_cagr_delta"],
                    operations=operations,
                    strategy_override=strategy,
                )
                next_strategy = _strategy_from_evaluation(
                    result, self.state_dir, research_run_id=evidence.run_id
                )
                if next_strategy is not None:
                    strategy = next_strategy
                evidence.finish_generation(number, str(result.get("status", "UNKNOWN")), result)
                elapsed = max(time.monotonic() - began, 0.000001)
                with self._connect() as db:
                    db.execute(
                        "INSERT INTO generation_history VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            job_id,
                            number,
                            elapsed,
                            request["method"],
                            request["count"],
                            parent_id,
                            strategy.strategy_id,
                            str(result.get("status", "UNKNOWN")),
                            json.dumps(result.get("counts", {})),
                            (
                                result.get("candidate_count", 0)
                                if isinstance(result.get("candidate_count", 0), int)
                                else 0
                            ),
                        ),
                    )
                    db.execute(
                        "UPDATE batches SET completed=?,heartbeat=? WHERE id=?",
                        (number, time.time(), job_id),
                    )
            evidence.finish_run("COMPLETED")
            with self._connect() as db:
                db.execute(
                    "UPDATE batches SET status='COMPLETED',finished=?,heartbeat=? WHERE id=?",
                    (time.time(), time.time(), job_id),
                )
        except (Exception, KeyboardInterrupt) as exc:
            if evidence is not None:
                try:
                    evidence.finish_run("FAILED")
                except EvidenceIntegrityError:
                    pass
            with self._connect() as db:
                db.execute(
                    "UPDATE batches SET status='FAILED',finished=?,error_code=? WHERE id=?",
                    (time.time(), type(exc).__name__, job_id),
                )
            raise
