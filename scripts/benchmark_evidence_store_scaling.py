"""Synthetic EvidenceStore scaling audit; never opens a real Quant state DB.

This pre-seeds valid rows in one SQLite transaction so timings are incremental
append/read costs at each size, NOT 10,000 sequential public append throughput.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import sqlite3
import statistics
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash
from memory.evidence_store import EvidenceIntegrityError, EvidenceStore, digest, encode

N_SAMPLES = (150, 1_000, 10_000)
APPEND_REPEATS = 11
READ_REPEATS = 5
ACCEPTANCE_MS = {
    150: {"append": 30.0, "read": 70.0},
    1_000: {"append": 60.0, "read": 150.0},
    10_000: {"append": 100.0, "read": 800.0},
}
MAX_READ_PYTHON_PEAK_MIB = 128.0
PAYLOAD_PADDING = "x" * 256


def payload(run_id: str, n: int) -> dict[str, object]:
    """Exactly one structurally valid, synthetic event for a registered run."""
    return {
        "research_run_id": run_id,
        "generation": n,
        "attempt_id": f"synthetic-{n}",
        "status": "COMPLETED",
        "synthetic_padding": PAYLOAD_PADDING,
    }


def seed(state: Path, size: int) -> EvidenceStore:
    """Create representative valid rows quickly, without claiming append timings."""
    store = EvidenceStore(state)
    run_id = f"synthetic-{size}"
    store.append("run", f"run:{run_id}", {
        "research_run_id": run_id, "requested_generations": size + APPEND_REPEATS + 5,
        "seed": 20261110,
    })
    if size > 1:
        with sqlite3.connect(store.path) as conn:
            conn.executemany(
                "INSERT INTO events(id, kind, payload, checksum) VALUES (?, ?, ?, ?)",
                (
                    (
                        f"generation:{run_id}:{i}", "generation",
                        encode(p := payload(run_id, i)),
                        digest([f"generation:{run_id}:{i}", "generation", p]),
                    )
                    for i in range(1, size)
                ),
            )
    assert len(store.events()) == size
    return store


def timed_samples(task: Any, n: int) -> list[float]:
    samples: list[float] = []
    for i in range(n):
        start = time.perf_counter_ns()
        task(i)
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return samples


def percentile(samples: list[float], proportion: float) -> float:
    return sorted(samples)[math.ceil(len(samples) * proportion) - 1]


def audit_lock_contention(store: EvidenceStore, size: int) -> dict[str, object]:
    """One real SQLite write lock for 150 ms, then a waiting append succeeds."""
    run_id = f"synthetic-{size}"
    begun = threading.Event()
    finished = threading.Event()
    problems: list[str] = []
    duration_ms: list[float] = []

    def waiting_append() -> None:
        begun.set()
        start = time.perf_counter_ns()
        try:
            store.append(
                "generation", f"lock:{run_id}",
                payload(run_id, size + APPEND_REPEATS + 2),
            )
            duration_ms.append((time.perf_counter_ns() - start) / 1e6)
        except Exception as exc:
            problems.append(type(exc).__name__ + ":" + str(exc))
        finally:
            finished.set()

    with sqlite3.connect(store.path, timeout=5, isolation_level=None) as blocking:
        blocking.execute("BEGIN IMMEDIATE")
        thread = threading.Thread(target=waiting_append, daemon=True)
        thread.start()
        assert begun.wait(2)
        # Allow thread to reach SQLite connect then wait under this write lock.
        time.sleep(0.15)
        blocking.execute("COMMIT")
    thread.join(timeout=7)
    if not finished.is_set() or problems or not duration_ms:
        raise AssertionError(f"concurrent append did not safely resume: {problems}")
    if duration_ms[0] < 140:
        raise AssertionError("contention test did not actually block a writer")
    return {"held_lock_ms": 150, "waiting_append_ms": round(duration_ms[0], 3),
            "completed": True, "error_count": len(problems)}


def audit_integrity(store: EvidenceStore, size: int) -> dict[str, object]:
    """The current API and SQLite triggers must still fail closed."""
    run_id = f"synthetic-{size}"
    before = len(store.events())
    try:
        store.append("attempt", f"invalid:{size}", {
            "research_run_id": run_id, "generation": 1, "attempt_id": "invalid",
            "status": "COMPLETED",
        })
    except EvidenceIntegrityError:
        pass
    else:
        raise AssertionError("invalid event unexpectedly committed")
    if len(store.events()) != before:
        raise AssertionError("invalid append changed the evidence count")
    with sqlite3.connect(store.path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise AssertionError("SQLite integrity check failed")
        trigger_guard = {}
        for operation, sql in [
            ("UPDATE", "UPDATE events SET kind='end' WHERE id=?"),
            ("DELETE", "DELETE FROM events WHERE id=?"),
        ]:
            try:
                conn.execute(sql, (f"run:{run_id}",))
            except sqlite3.IntegrityError:
                trigger_guard[operation] = True
            else:
                raise AssertionError(f"immutable {operation} succeeded")
            conn.rollback()
        if conn.execute("SELECT count(*) FROM events").fetchone()[0] != before:
            raise AssertionError("immutable trigger lost a row")
    if len(store.events()) != before:
        raise AssertionError("checksum verification changed events")
    return {
        "integrity_check": integrity, "update_prohibited": trigger_guard["UPDATE"],
        "delete_prohibited": trigger_guard["DELETE"],
        "invalid_append_rolled_back": True,
        "checksums_all_verified": True,
    }


def benchmark(size: int, root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"quant-t15-{size}-", dir=root) as directory:
        store = seed(Path(directory) / "state", size)
        run_id = f"synthetic-{size}"

        def do_append(i: int) -> None:
            store.append("generation", f"bench:{run_id}:{i}",
                         payload(run_id, size + i + 1))

        append_times = timed_samples(do_append, APPEND_REPEATS)

        def do_read(_i: int) -> None:
            result = store.events()
            if len(result) != size + APPEND_REPEATS:
                raise AssertionError("read lost an event")

        read_times = timed_samples(do_read, READ_REPEATS)
        gc.collect()
        tracemalloc.start()
        store.events()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_peak = peak / 2**20
        integrity = audit_integrity(store, size)
        contention = audit_lock_contention(store, size)
        count = len(store.events())
        with sqlite3.connect(store.path) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise AssertionError("database corrupted after concurrency test")
        measurements: dict[str, Any] = {
            "append_count_before": size, "append_repeats": APPEND_REPEATS,
            "read_repeats": READ_REPEATS, "count_after": count,
            "append_ms_samples": [round(x, 3) for x in append_times],
            "read_ms_samples": [round(x, 3) for x in read_times],
            "append_p50_ms": round(statistics.median(append_times), 3),
            "append_p95_ms": round(percentile(append_times, 0.95), 3),
            "read_p50_ms": round(statistics.median(read_times), 3),
            "read_p95_ms": round(percentile(read_times, 0.95), 3),
            "read_tracemalloc_peak_mib": round(memory_peak, 3),
            "read_tracemalloc_current_mib": round(current / 2**20, 3),
            "db_size_bytes": store.path.stat().st_size,
            "integrity": integrity,
            "contention": contention,
        }
        limits = ACCEPTANCE_MS[size]
        measurements["thresholds_passed"] = {
            "append_p95": measurements["append_p95_ms"] <= limits["append"],
            "read_p95": measurements["read_p95_ms"] <= limits["read"],
            "read_peak_memory": memory_peak <= MAX_READ_PYTHON_PEAK_MIB,
            "integrity": all(v is True or v == "ok" for v in integrity.values()),
            "lock_completed": contention["completed"],
        }
        return measurements


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temp-root", type=Path, default=Path("/shared"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.temp_root.is_dir():
        parser.error("temporary root must already exist")
    started = time.perf_counter()
    result: dict[str, Any] = {
        "schema": "QUANT_T15_SYNTHETIC_SCALING_V1",
        "environment": {
            "os": platform.platform(), "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version, "cpu_count": os.cpu_count(),
            "temp_root": str(args.temp_root),
        },
        "fixture": {
            "source": "SYNTHETIC_NOT_EXISTING_G150_OR_LIVE_MARKET",
            "pad_bytes_per_row": len(PAYLOAD_PADDING),
            "seed_method": "one transaction SQL bulk setup + public append benchmark",
            "not_claimed": "10,000 sequential EvidenceStore.append operations",
            "initial_sizes": list(N_SAMPLES),
        },
        # String keys are required before hashing: JSON converts integer
        # dictionary keys into strings and can change canonical key ordering.
        "predeclared_thresholds_ms": {
            str(n): limits for n, limits in ACCEPTANCE_MS.items()
        },
        "read_memory_limit_mib": MAX_READ_PYTHON_PEAK_MIB,
        "sizes": {},
    }
    for size in N_SAMPLES:
        score = benchmark(size, args.temp_root)
        result["sizes"][str(size)] = score
        print(size, "append_p95_ms", score["append_p95_ms"],
              "read_p95_ms", score["read_p95_ms"],
              "peak_mib", score["read_tracemalloc_peak_mib"],
              "thresholds", score["thresholds_passed"], flush=True)
    result["seconds_total"] = round(time.perf_counter() - started, 3)
    result["result_hash"] = content_hash(result)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
    print("FROZEN_SYNTHETIC_RESULT", result["result_hash"])


if __name__ == "__main__":
    main()
