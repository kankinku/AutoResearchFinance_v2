"""Durable GPT-directed, bounded batch research and measured per-generation ETA.

No LLM process is used by the batch executor. GPT provides the validated plan
once; deterministic local evaluation chooses only audited eligible successors.
"""

from __future__ import annotations

import hashlib
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
from application.research_batch_summary import explain_batch_attempts
from application.research_hypothesis import (
    LocalHypothesis,
    propose_next_hypothesis,
    verified_failed_gates,
)
from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from core.data.quality import market_data_quality
from core.features.registry import research_feature_specs
from experiments.candidate_generator import generate_candidates
from experiments.deduplicator import deduplicate_candidates
from experiments.identity import semantic_strategy_hash
from memory.evidence_store import EvidenceIntegrityError, EvidenceStore
from mutation.engine import MutationOperation, apply_operations
from mutation.parameter import ParameterDomain
from orchestration.evaluation_runner import (
    ALLOWED_STRATEGY_SUFFIXES,
    parse_parameter_domains,
    resolve_project_input,
)
from orchestration.evidence import require_research_zone
from research.llm.director import ResearchIntent
from research.llm.intent_bridge import apply_intent, intent_to_operations
from runtime.evidence_session import EvidenceSession
from runtime.process_lifecycle import process_matches
from runtime.research_loop import _strategy_from_evaluation
from strategy_ir.normalizer import normalize_source
from strategy_ir.schema import StrategyIR

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


def _should_stop_exhausted_generation(
    *,
    result_status: str,
    method: str,
    initial_domains: tuple[ParameterDomain, ...],
    pending_hypothesis: LocalHypothesis | None,
) -> bool:
    """Do not discard a new evidence-guided hypothesis when a local grid exhausts."""
    return (
        result_status == "NO_NEW_CANDIDATES"
        and pending_hypothesis is None
        and (method == "grid" or not initial_domains)
    )


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

    def _registered_partner(self, parent_id: str) -> tuple[Path, StrategyIR]:
        """Resolve exactly one non-symlinked, normalized catalog parent."""
        matches: list[tuple[Path, StrategyIR]] = []
        for path in sorted((self.project_root / "strategies" / "normalized").glob("*.json")):
            if path.is_symlink():
                continue
            imported = normalize_source(path)
            if imported.strategy is not None and imported.strategy.strategy_id == parent_id:
                matches.append((path, imported.strategy))
        if len(matches) != 1:
            raise BatchRequestError(
                "UNREGISTERED_CROSSOVER_PARENT",
                "Second mixed-mode parent must uniquely match a normalized registered strategy.",
            )
        return matches[0]

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
            "parameter_domains",
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
        if (
            len(intent.parent_ids) not in (1, 2)
            or intent.parent_ids[0] != imported.strategy.strategy_id
            or (len(intent.parent_ids) == 2 and intent.mode != "mixed")
        ):
            raise BatchRequestError(
                "PARENT_ID_MISMATCH",
                "The first parent must match source_path; an optional second registered "
                "parent is accepted only in mixed research mode.",
            )
        partner_path: Path | None = None
        partner_hash: str | None = None
        if len(intent.parent_ids) == 2:
            if intent.parent_ids[1] == intent.parent_ids[0]:
                raise BatchRequestError("DUPLICATE_CROSSOVER_PARENT", "Parents must be different.")
            partner_path, _ = self._registered_partner(intent.parent_ids[1])
            partner_hash = hashlib.sha256(partner_path.read_bytes()).hexdigest()
        if intent.primitive_request is not None:
            raise ValueError("unregistered primitive requests cannot be executed")
        feature_specs = research_feature_specs()
        intent_to_operations(intent, feature_specs)
        parent_after_intent = apply_intent(imported.strategy, intent, feature_specs)
        domains = parse_parameter_domains(args.get("parameter_domains"))
        if len(domains) > 4 or any(len(domain.values) > 24 for domain in domains):
            raise BatchRequestError(
                "PARAMETER_DOMAIN_TOO_LARGE", "At most 4 domains of 24 values are supported."
            )
        if len({domain.name for domain in domains}) != len(domains):
            raise BatchRequestError(
                "DUPLICATE_PARAMETER_DOMAIN", "Parameter domain names must be unique."
            )
        for domain in domains:
            if not (
                (
                    domain.name.startswith("indicators.")
                    and (domain.name.endswith(".period") or ".parameters." in domain.name)
                )
                or domain.name
                in {
                    "risk.stop_loss_pct",
                    "risk.take_profit_pct",
                    "risk.trailing_stop_pct",
                    "risk.position_size_pct",
                    "risk.risk_appetite",
                    "risk.loss_tolerance_pct",
                    "risk.daily_loss_limit_pct",
                    "risk.daily_loss_action",
                    "risk.max_concurrent_positions",
                    "risk.max_total_exposure_pct",
                }
            ):
                raise BatchRequestError(
                    "INVALID_PARAMETER_DOMAIN", "Only indicator/risk parameter paths are allowed."
                )
            for value in domain.values:
                try:
                    apply_operations(
                        parent_after_intent,
                        [MutationOperation("SET_PARAMETER", domain.name, value)],
                    )
                except ValueError as exc:
                    raise BatchRequestError(
                        "INVALID_PARAMETER_DOMAIN",
                        "Domain values must be valid for the selected strategy parameter.",
                    ) from exc
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
            "partner_source_path": (
                partner_path.relative_to(self.project_root).as_posix() if partner_path else None
            ),
            "partner_source_hash": partner_hash,
            "parameter_domains": [
                {"name": domain.name, "values": list(domain.values)} for domain in domains
            ],
            "generations": generations,
            "count": count,
            "method": method,
            "seed": seed,
            "min_trades": min_trades,
            "min_annual_trades": min_annual,
            "min_qqq_cagr_delta": delta,
        }

    def preflight(self, args: dict[str, Any]) -> dict[str, object]:
        """Read-only validation and a bounded candidate-diversity preview.

        A preview is not an evaluated strategy or a guarantee that later
        generations will keep the same parent after an eligible successor.
        """
        request = self._validate_request(args)
        data_path = self.project_root / request["data_path"]
        try:
            require_research_zone(data_path)
            data = ParquetDataProvider.read(data_path)
            if DataZone(data.zone) is not DataZone.DEVELOPMENT:
                raise BatchRequestError(
                    "DATA_ZONE_DENIED", "Batch research requires development-only market data."
                )
            if not data.bars:
                raise BatchRequestError("INSUFFICIENT_HISTORY", "Dataset contains no price bars.")
        except BatchRequestError:
            raise
        except EvidenceIntegrityError as exc:
            raise BatchRequestError(
                "DATA_ZONE_DENIED", "Research requires development-only market data."
            ) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise BatchRequestError(
                "INVALID_DATASET", "Research data is not a valid development OHLCV Parquet."
            ) from exc
        # Reject corrupted series data before queuing, without exposing its rows.
        if request["series_data_path"] is not None:
            try:
                require_research_zone(self.project_root / request["series_data_path"])
                series = ParquetDataProvider.read_series(
                    self.project_root / request["series_data_path"]
                )
                if DataZone(series.zone) is not DataZone.DEVELOPMENT:
                    raise BatchRequestError(
                        "DATA_ZONE_DENIED", "Research series must be development-only."
                    )
            except BatchRequestError:
                raise
            except EvidenceIntegrityError as exc:
                raise BatchRequestError(
                    "DATA_ZONE_DENIED", "Research series must be development-only."
                ) from exc
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise BatchRequestError("INVALID_DATASET", "Research series is invalid.") from exc
        result = normalize_source(self.project_root / request["source_path"])
        if result.strategy is None:
            raise BatchRequestError("INVALID_SOURCE", "Research strategy cannot be normalized.")
        intent = ResearchIntent.model_validate(request["intent"])
        operations = tuple(intent_to_operations(intent, research_feature_specs()))
        domains = parse_parameter_domains(request["parameter_domains"])
        seen: set[str] = set()
        generated = 0
        # At most five generations * 64 candidates. No evaluation or DB mutation.
        preview_generations = min(request["generations"], 5)
        for number in range(preview_generations):
            candidates = generate_candidates(
                result.strategy,
                operations,
                domains,
                method=request["method"],
                count=request["count"],
                seed=request["seed"] + number,
            )
            generated += len(candidates)
            seen.update(semantic_strategy_hash(candidate.strategy) for candidate in candidates)
        duplicates = generated - len(seen)
        warnings: list[str] = []
        if duplicates:
            warnings.append("PREVIEW_REPEATS_STRATEGIES")
        if request["generations"] > preview_generations:
            warnings.append("PREVIEW_ONLY_FIRST_FIVE_GENERATIONS")
        quality = market_data_quality(data)
        if quality.issues:
            warnings.append("DATA_PROVENANCE_UNVERIFIED")
        if request["intent"]["mode"] == "mixed":
            warnings.append("ADAPTIVE_PREVIEW_ONLY_INITIAL_FIXED_PLAN")
        return {
            "status": "READY_WITH_WARNINGS" if warnings or not seen else "READY",
            "source_path": request["source_path"],
            "strategy_id": result.strategy.strategy_id,
            "data_path": request["data_path"],
            "dataset": {
                "dataset_hash": data.dataset_hash,
                "dataset_version": data.version,
                "zone": DataZone(data.zone).value,
                "bars": len(data.bars),
                "symbols": sorted({bar.symbol for bar in data.bars}),
                "quality": quality.record(),
            },
            "preview_generations": preview_generations,
            "preview_candidate_instances": generated,
            "preview_unique_strategies": len(seen),
            "preview_duplicate_candidates": duplicates,
            "repetition_risk": duplicates > 0,
            "warnings": warnings,
            "preview_only": True,
            "adaptive_replanning_enabled": request["intent"]["mode"] == "mixed",
            "orders_enabled": False,
        }

    def describe_inputs(self) -> dict[str, object]:
        """Small, read-only catalog for choosing usable GPT research inputs."""
        sources: list[dict[str, object]] = []
        directory = self.project_root / "strategies" / "normalized"
        for path in sorted(directory.glob("*.json"))[:100]:
            if path.is_symlink():
                continue
            try:
                validated = resolve_project_input(
                    self.project_root,
                    path.relative_to(self.project_root).as_posix(),
                    ALLOWED_STRATEGY_SUFFIXES,
                )
                strategy = normalize_source(validated).strategy
                if strategy is not None:
                    sources.append(
                        {
                            "source_path": validated.relative_to(self.project_root).as_posix(),
                            "strategy_id": strategy.strategy_id,
                            "family": strategy.family,
                            "indicators": [
                                {"name": name, "type": spec.type}
                                for name, spec in sorted(strategy.indicators.items())
                            ],
                            "numeric_parameter_paths": [
                                f"indicators.{name}.period"
                                for name, spec in sorted(strategy.indicators.items())
                                if spec.period is not None
                            ],
                        }
                    )
            except (OSError, ValueError, PermissionError):
                continue

        datasets: list[dict[str, object]] = []
        candidates = list(self.project_root.glob("*.parquet"))
        for dirname in ("data", "datasets"):
            candidates.extend((self.project_root / dirname).rglob("*.parquet"))
        for path in sorted(set(candidates))[:200]:
            if path.is_symlink():
                continue
            try:
                checked = resolve_project_input(
                    self.project_root,
                    path.relative_to(self.project_root).as_posix(),
                    frozenset({".parquet"}),
                )
                # Check only Parquet metadata before touching any data rows.
                # Protected zones must never appear in the research catalog.
                require_research_zone(checked)
                data = ParquetDataProvider.read(checked)
                if DataZone(data.zone) is not DataZone.DEVELOPMENT or not data.bars:
                    continue
                quality = market_data_quality(data)
                datasets.append(
                    {
                        "data_path": checked.relative_to(self.project_root).as_posix(),
                        "zone": "development",
                        "symbols": sorted({bar.symbol for bar in data.bars}),
                        "timeframe": data.timeframe,
                        "bars": len(data.bars),
                        "quality_status": quality.status,
                        "point_in_time_verified": quality.point_in_time_verified,
                    }
                )
            except (
                OSError,
                ValueError,
                PermissionError,
                EvidenceIntegrityError,
                KeyError,
                TypeError,
            ):
                continue

        return {
            "sources": sources,
            "data_paths": [item["data_path"] for item in datasets],
            "datasets": datasets,
            "ready_for_batch": bool(sources and datasets),
            "readiness_scope": "INPUTS_DISCOVERED_ONLY",
            "requires_preflight": True,
            "note": (
                "Choose a registered strategy by family and a development dataset by symbol. "
                "Check parameter paths against Strategy IR and run preflight before executing. "
                "For failure-led local hypotheses select ResearchIntent mode=mixed. "
                "Mixed mode reuses development data and is not independent OOS. "
                "Catalog visibility is not performance validation."
            ),
        }

    def start(self, args: dict[str, Any]) -> dict[str, object]:
        preview = self.preflight(args)
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
        return {**self.status(job_id), "preflight": preview}

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
                "SELECT seconds,result_status FROM generation_history "
                "WHERE batch_id=? ORDER BY generation",
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
        # Only deterministic, fixed search spaces may stop without sampling
        # later seeds. No completed attempts are fabricated for skipped generations.
        exhausted = (
            row["status"] == "COMPLETED"
            and row["completed"] < row["requested"]
            and bool(durations)
            and durations[-1]["result_status"] == "NO_NEW_CANDIDATES"
        )
        # If no samples, do NOT invent an ETA.
        return {
            "job_id": row["id"],
            "status": row["status"],
            "requested_generations": row["requested"],
            "completed_generations": row["completed"],
            "stopped_early": exhausted,
            "stop_reason": "SEARCH_SPACE_EXHAUSTED" if exhausted else None,
            "unexecuted_generations": (row["requested"] - row["completed"] if exhausted else 0),
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
        generations: list[dict[str, object]] = []
        for row in rows:
            counts = json.loads(row["result_counts"])
            skipped = counts.pop("DUPLICATE_SKIPPED", None)
            generations.append(
                {
                    "generation": row["generation"],
                    "duration_seconds": round(row["seconds"], 3),
                    "parent_id": row["parent_id"],
                    "successor_id": row["successor_id"],
                    "status": row["result_status"],
                    "candidate_count": row["candidate_count"],
                    "counts": counts,
                    "duplicate_skipped": skipped,
                }
            )
        # Generation count is not necessarily the number of independent strategy
        # candidates. Count verified candidate hashes from immutable attempt Evidence.
        hashes: list[str] = []
        attempts: list[dict[str, object]] = []
        generation_hypotheses: dict[int, dict[str, object]] = {}
        if isinstance(status["research_run_id"], str):
            for event in EvidenceStore(self.state_dir).events():
                payload = event["payload"]
                if (
                    event["kind"] == "generation"
                    and payload.get("research_run_id") == status["research_run_id"]
                    and isinstance(payload.get("generation"), int)
                ):
                    generation_hypotheses[payload["generation"]] = {
                        "next_hypothesis": payload.get("next_hypothesis"),
                        "applied_hypothesis": payload.get("applied_hypothesis"),
                        "replanning_status": payload.get("replanning_status"),
                    }
                if (
                    event["kind"] == "attempt"
                    and payload.get("research_run_id") == status["research_run_id"]
                ):
                    attempts.append(payload)
                    for candidate in payload.get("candidates", []):
                        candidate_hash = candidate.get("candidate_hash")
                        if isinstance(candidate_hash, str) and candidate_hash:
                            hashes.append(candidate_hash)
        for row in generations:
            row.update(generation_hypotheses.get(cast(int, row["generation"]), {}))
        configured = json.loads(self._job(str(status["job_id"]))["request_json"])
        is_adaptive = (
            isinstance(configured.get("intent"), dict)
            and configured["intent"].get("mode") == "mixed"
        )
        distinct = len(set(hashes))
        duplicate = len(hashes) - distinct
        promotions = sum(item["parent_id"] != item["successor_id"] for item in generations)
        return {
            **status,
            "generations": generations,
            "total_measured_seconds": round(sum(float(r["seconds"]) for r in rows), 3),
            "evaluated_candidate_instances": len(hashes),
            "unique_candidate_count": distinct if hashes else None,
            "duplicate_candidate_evaluations": duplicate if hashes else None,
            "repeated_candidate_warning": duplicate > 0,
            "promoted_successor_generations": promotions,
            "total_skipped_duplicate_candidates": (
                sum(cast(int, item["duplicate_skipped"]) for item in generations)
                if generations
                and all(isinstance(item["duplicate_skipped"], int) for item in generations)
                else None
            ),
            "skipped_duplicate_generations": sum(
                item["status"] == "NO_NEW_CANDIDATES" for item in generations
            ),
            "candidate_uniqueness_basis": "immutable_evidence" if hashes else "not_measured",
            "research_intent_mode": (
                "mixed_evidence_guided_local" if is_adaptive else "fixed_intent"
            ),
            "adaptive_replanned_generations": sum(
                row.get("next_hypothesis") is not None for row in generations
            ),
            "adaptive_applied_generations": sum(
                row.get("applied_hypothesis") is not None for row in generations
            ),
            "final_report_ready": status["status"] in _TERMINAL,
            "oos_approved": False,
            "failure_analysis": explain_batch_attempts(attempts),
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
            partner: StrategyIR | None = None
            if len(intent.parent_ids) == 2:
                partner_path = resolve_project_input(
                    self.project_root,
                    request["partner_source_path"],
                    frozenset({".json"}),
                )
                if (
                    hashlib.sha256(partner_path.read_bytes()).hexdigest()
                    != request["partner_source_hash"]
                ):
                    raise EvidenceIntegrityError(
                        "registered crossover parent changed since preflight"
                    )
                partner = normalize_source(partner_path).strategy
                if partner is None or partner.strategy_id != intent.parent_ids[1]:
                    raise EvidenceIntegrityError("registered crossover parent identity mismatch")
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
            seen_semantics: set[str] = set()
            domains = parse_parameter_domains(request.get("parameter_domains"))
            adaptive = intent.mode == "mixed"
            next_hypothesis: LocalHypothesis | None = None
            used_hypotheses: set[str] = set()
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
                applied = next_hypothesis
                evaluation_operations = applied.operations if applied is not None else operations
                evaluation_domains = applied.domains if applied is not None else domains
                next_hypothesis = None
                # Successor is adopted ONLY from auditable eligible immutable Evidence.
                candidates = deduplicate_candidates(
                    list(
                        generate_candidates(
                            strategy,
                            tuple(evaluation_operations),
                            evaluation_domains,
                            method=request["method"],
                            count=request["count"],
                            seed=request["seed"] + number - 1,
                        )
                    ),
                    semantic=True,
                ).unique
                semantics = {semantic_strategy_hash(item.strategy) for item in candidates}
                skipped = len(semantics & seen_semantics)
                if semantics and semantics <= seen_semantics:
                    # The same effective strategy on immutable data need not be
                    # evaluated again. This generation is recorded, not invented.
                    result: dict[str, object] = {
                        "status": "NO_NEW_CANDIDATES",
                        "candidate_count": 0,
                        "counts": {},
                        "duplicate_skipped": skipped,
                    }
                else:
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
                        operations=evaluation_operations,
                        parameter_domains=evaluation_domains,
                        strategy_override=strategy,
                        excluded_semantic_hashes=tuple(sorted(seen_semantics)),
                    )
                    if result.get("duplicate_skipped") != skipped:
                        raise EvidenceIntegrityError("evaluated candidate exclusion mismatch")
                seen_semantics.update(semantics)
                next_strategy = _strategy_from_evaluation(
                    result, self.state_dir, research_run_id=evidence.run_id
                )
                if applied is not None:
                    result["applied_hypothesis"] = applied.summary()
                if next_strategy is not None:
                    strategy = next_strategy
                if adaptive and next_strategy is None and number < request["generations"]:
                    attempt_id = result.get("attempt_id")
                    feedback = (
                        verified_failed_gates(
                            evidence.store.events(),
                            run_id=evidence.run_id,
                            attempt_id=attempt_id,
                        )
                        if isinstance(attempt_id, str)
                        else None
                    )
                    if feedback and isinstance(attempt_id, str):
                        next_hypothesis = propose_next_hypothesis(
                            parent=strategy,
                            initial_operations=tuple(operations),
                            initial_domains=domains,
                            gate_names=feedback,
                            prior_attempt_id=attempt_id,
                            used_hypotheses=frozenset(used_hypotheses),
                            already_evaluated=frozenset(seen_semantics),
                            method=request["method"],
                            count=request["count"],
                            next_seed=request["seed"] + number,
                            partner=partner,
                        )
                        if next_hypothesis is not None:
                            used_hypotheses.add(next_hypothesis.reason_code)
                            result["next_hypothesis"] = next_hypothesis.summary()
                        else:
                            result["replanning_status"] = "NO_SAFE_NOVEL_HYPOTHESIS"
                    else:
                        result["replanning_status"] = "NO_VERIFIED_REJECTION_FEEDBACK"
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
                            json.dumps(
                                {
                                    **cast(dict[str, int], result.get("counts", {})),
                                    "DUPLICATE_SKIPPED": result.get("duplicate_skipped", 0),
                                }
                            ),
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
                if _should_stop_exhausted_generation(
                    result_status=str(result.get("status")),
                    method=request["method"],
                    initial_domains=domains,
                    pending_hypothesis=next_hypothesis,
                ):
                    # Further seeds cannot introduce an unseen strategy with
                    # grid search, or in the absence of parameter domains.
                    break
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
