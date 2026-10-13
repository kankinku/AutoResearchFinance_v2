"""One-hour, multi-family paper-research campaign using durable batch workers.

A controller runs until the wall-time deadline; generation counts only bound
individual constituent batches. No LLM requests, sealed OOS, or broker orders.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from application.research_batch_service import ResearchBatchService

DATA_PATH = "data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet"
ORDER = (
    "mean_reversion",
    "momentum",
    "week52_high",
    "volatility",
    "golden_cross",
    "consecutive",
    "breakout_fail",
    "strong_close",
    "trend_filter",
    "disparity",
)
TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"})
RISK_FIELDS: dict[str, list[int | float]] = {
    "risk.stop_loss_pct": [1.5, 2, 3, 4, 5, 6, 8, 10, 12, 15],
    "risk.take_profit_pct": [0, 2, 3, 5, 7, 10, 12, 15, 20],
    "risk.trailing_stop_pct": [0, 2, 3, 4, 5, 7, 10],
    "risk.position_size_pct": [15, 25, 35, 45, 55, 65, 75, 85, 95, 100],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def domains_for(source: dict[str, Any], cycle: int, index: int) -> list[dict[str, Any]]:
    """Produce different permitted parameter domains, never executable code."""
    indicator_paths = list(source["numeric_parameter_paths"])
    domains: list[dict[str, Any]] = []
    for number, path in enumerate(indicator_paths[:2]):
        slow = "slow" in path or "52w" in path or "high_52w" in path
        low = 15 + (cycle % 3) * 5 if slow else 2 + (cycle % 4) * 3
        high = low + (72 if slow else 30)
        values = list(range(low, high + 1, 3))[:24]
        # Favor separation between crossover lookback periods.
        if number and len(indicator_paths) > 1 and "slow" in path:
            values = [v for v in values if v >= 24]
        domains.append({"name": path, "values": values})
    rotating = list(RISK_FIELDS)
    selected = [rotating[(index + cycle + n) % len(rotating)] for n in range(4)]
    for path in selected:
        if len(domains) == 4:
            break
        domains.append({"name": path, "values": RISK_FIELDS[path]})
    return domains


def build_request(
    source: dict[str, Any],
    *,
    index: int,
    batch_generations: int,
    candidates: int,
    data_path: str = DATA_PATH,
) -> dict[str, Any]:
    cycle = index // len(ORDER)
    mode = "mixed" if cycle % 2 == 0 else "parameter"
    return {
        "source_path": source["source_path"],
        "data_path": data_path,
        "intent": {
            "mode": mode,
            "parent_ids": [source["strategy_id"]],
            "operations": [],
            "rationale": (
                "Bounded, diversified exploratory QQQ paper research: "
                "rotate strategy family, risk and indicator domains; "
                "preserve immutable Evidence; no orders or sealed OOS."
            ),
        },
        "generations": batch_generations,
        "count": candidates,
        "method": "random" if index % 3 else "bayesian",
        "seed": 20261013 + index * 71,
        "min_trades": 5,
        "min_annual_trades": 5,
        # The independently timestamped QQQ/NASDAQ benchmark SeriesDataSet
        # is NOT available. Never set a numeric delta on a missing benchmark.
        "parameter_domains": domains_for(source, cycle, index),
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _event(directory: Path, kind: str, **fields: Any) -> None:
    line = {"at_utc": utc_now(), "event": kind, **fields}
    with (directory / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def run(
    *,
    project_root: Path,
    state_dir: Path,
    duration_seconds: int,
    batch_generations: int,
    candidates: int,
    campaign_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    service = ResearchBatchService(project_root=project_root, state_dir=state_dir)
    inventory = service.describe_inputs()
    sources = cast(list[dict[str, Any]], inventory["sources"])
    datasets = cast(list[dict[str, Any]], inventory["datasets"])
    registered = {item["strategy_id"]: item for item in sources}
    chosen = [registered[key] for key in ORDER if key in registered]
    if not chosen or not datasets:
        raise RuntimeError("No registered development research inputs")
    data_paths = {item["data_path"] for item in datasets}
    if DATA_PATH not in data_paths:
        raise RuntimeError("QQQ development input not present in the managed catalog")
    # Verify every family with the real canonical read-only preflight before
    # starting the wall-clock timer or spawning any worker.
    checks: list[dict[str, str]] = []
    allowed: list[dict[str, Any]] = []
    for index, source in enumerate(chosen):
        request = build_request(
            source, index=index, batch_generations=batch_generations, candidates=candidates
        )
        try:
            result = service.preflight(request)
            allowed.append(source)
            checks.append(
                {
                    "strategy": source["strategy_id"],
                    "family": source["family"],
                    "status": str(result["status"]),
                }
            )
        except (ValueError, OSError) as exc:
            checks.append(
                {
                    "strategy": source["strategy_id"],
                    "family": source["family"],
                    "status": f"BLOCKED:{type(exc).__name__}",
                }
            )
    if dry_run:
        return {"dry_run": True, "eligible_sources": len(allowed), "checks": checks}
    if len(allowed) < 5:
        raise RuntimeError("Fewer than five diverse strategy inputs passed preflight")

    campaign_root = state_dir / "system" / "timed-diverse-research"
    campaign_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = campaign_root / "active.lock"
    # Exclusive OS-level creation prevents two distinct controllers from
    # accidentally consuming the same single-worker research queue.
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("A timed research controller is already registered") from exc
    directory = campaign_root / campaign_id
    directory.mkdir(mode=0o700)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(campaign_id + "\n")
    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc)
    end_at = started_at + timedelta(seconds=duration_seconds)
    summary: dict[str, Any] = {
        "campaign_id": campaign_id,
        "status": "RUNNING",
        "started_at_utc": started_at.isoformat(),
        "deadline_at_utc": end_at.isoformat(),
        "duration_seconds": duration_seconds,
        "elapsed_seconds": 0,
        "orders_enabled": False,
        "sealed_oos": "NOT_MEASURED",
        "independent_pit_data": False,
        "benchmark_qqq_delta": "NOT_MEASURED",
        "selected_dataset": DATA_PATH,
        "preflight": checks,
        "batches_started": 0,
        "batches_completed": 0,
        "generations_completed": 0,
        "evaluated_candidates": 0,
        "successful_candidates": 0,
        "failure_count": 0,
        "families_visited": [],
        "strategy_ids_visited": [],
        "current_job_id": None,
        "batch_records": [],
    }
    _atomic_json(directory / "status.json", summary)
    _event(directory, "campaign_started", deadline=end_at.isoformat(), sources=len(allowed))
    current_job: str | None = None
    try:
        iteration = 0
        while time.monotonic() - started_monotonic < duration_seconds:
            if (directory / "STOP").exists():
                summary["status"] = "STOP_REQUESTED"
                break
            remaining = duration_seconds - (time.monotonic() - started_monotonic)
            if remaining < 12:
                break
            source = allowed[iteration % len(allowed)]
            request = build_request(
                source,
                index=iteration,
                batch_generations=batch_generations,
                candidates=candidates,
            )
            iteration += 1
            try:
                # Respect an external user's active batch; never cancel or
                # preempt a job that is not owned by this campaign.
                latest = None
                try:
                    latest = service.status()
                except ValueError:
                    pass
                if latest and latest["status"] in {"QUEUED", "RUNNING"}:
                    _event(directory, "external_batch_active", job_id=latest["job_id"])
                    time.sleep(min(3, remaining))
                    continue
                started = service.start(request)
                current_job = str(started["job_id"])
                summary["current_job_id"] = current_job
                summary["batches_started"] += 1
                for field, item in [
                    ("families_visited", source["family"]),
                    ("strategy_ids_visited", source["strategy_id"]),
                ]:
                    if item not in summary[field]:
                        summary[field].append(item)
                _event(
                    directory,
                    "batch_started",
                    job_id=current_job,
                    strategy=source["strategy_id"],
                    family=source["family"],
                    generations=batch_generations,
                    candidates=candidates,
                    search_method=request["method"],
                    parameters=[d["name"] for d in request["parameter_domains"]],
                )
                while True:
                    status = service.status(current_job)
                    summary["current_completed_generations"] = status["completed_generations"]
                    summary["elapsed_seconds"] = round(time.monotonic() - started_monotonic, 1)
                    _atomic_json(directory / "status.json", summary)
                    if status["status"] in TERMINAL:
                        break
                    if time.monotonic() - started_monotonic >= duration_seconds:
                        service.cancel(current_job)
                        _event(directory, "deadline_cancel_requested", job_id=current_job)
                        # Wait for the current generation to finish. Never force-kill
                        # a worker while it is committing immutable Evidence.
                        for _ in range(40):
                            time.sleep(1)
                            status = service.status(current_job)
                            if status["status"] in TERMINAL:
                                break
                        break
                    if (directory / "STOP").exists():
                        service.cancel(current_job)
                        _event(directory, "operator_cancel_requested", job_id=current_job)
                    time.sleep(2)
                if status["status"] in TERMINAL:
                    report = service.report(current_job)
                    record = {
                        "job_id": current_job,
                        "research_run_id": report["research_run_id"],
                        "strategy": source["strategy_id"],
                        "family": source["family"],
                        "status": report["status"],
                        "generations": report["completed_generations"],
                        "evaluated_candidates": report["evaluated_candidate_instances"],
                        "promotions": report["promoted_successor_generations"],
                        "skipped_duplicates": report["total_skipped_duplicate_candidates"],
                        "duration_seconds": report["total_measured_seconds"],
                    }
                    summary["batch_records"].append(record)
                    summary["batches_completed"] += 1
                    summary["generations_completed"] += int(record["generations"])
                    summary["evaluated_candidates"] += int(record["evaluated_candidates"] or 0)
                    summary["successful_candidates"] += int(record["promotions"] or 0)
                    _event(directory, "batch_finished", **record)
                else:
                    summary["status"] = "CANCELLATION_PENDING"
                    _event(
                        directory,
                        "batch_cancellation_pending",
                        job_id=current_job,
                        status=status["status"],
                    )
                    break
            except (OSError, RuntimeError, ValueError) as exc:
                summary["failure_count"] += 1
                _event(
                    directory,
                    "batch_failure",
                    strategy=source["strategy_id"],
                    error_type=type(exc).__name__,
                )
                time.sleep(1)
            finally:
                summary["elapsed_seconds"] = round(time.monotonic() - started_monotonic, 1)
                _atomic_json(directory / "status.json", summary)
                current_job = None
                summary["current_job_id"] = None
        if summary["status"] == "RUNNING":
            summary["status"] = "COMPLETED_TIME_BUDGET"
    except BaseException:
        summary["status"] = "CONTROLLER_INTERRUPTED"
        if current_job:
            service.cancel(current_job)
        raise
    finally:
        summary["elapsed_seconds"] = round(time.monotonic() - started_monotonic, 1)
        summary["ended_at_utc"] = utc_now()
        _atomic_json(directory / "status.json", summary)
        _event(directory, "campaign_finished", status=summary["status"])
        if lock.exists() and lock.read_text(encoding="utf-8").strip() == campaign_id:
            lock.unlink()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--batch-generations", type=int, default=14)
    parser.add_argument("--candidates", type=int, default=6)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 10 <= args.duration_seconds <= 86400:
        parser.error("duration_seconds must be in [10, 86400]")
    if not 1 <= args.batch_generations <= 100:
        parser.error("batch_generations must be in [1, 100]")
    if not 1 <= args.candidates <= 64:
        parser.error("candidates must be in [1, 64]")
    campaign_id = args.campaign_id or "hour-" + uuid4().hex[:12]
    response = run(
        project_root=args.project_root,
        state_dir=args.state_dir,
        duration_seconds=args.duration_seconds,
        batch_generations=args.batch_generations,
        candidates=args.candidates,
        campaign_id=campaign_id,
        dry_run=args.dry_run,
    )
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
