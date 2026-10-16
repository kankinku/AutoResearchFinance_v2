"""Strict read-only observer of supplemental MCP generation wall-clock intervals.

Old generations intentionally have no timing, because canonical S7/generation
records did not contain timestamps. No inference from file mtime or event logs.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


class TimingEvidenceError(ValueError):
    """Malformed or inconsistent sidecar records; do not invent elapsed time."""


def _time(value: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise TimingEvidenceError('INVALID_GENERATION_TIME')
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TimingEvidenceError('INVALID_GENERATION_TIME') from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise TimingEvidenceError('NAIVE_GENERATION_TIME')
    return dt.astimezone(timezone.utc)


def generation_timing(
    gateway: sqlite3.Connection, *, session_id: str, completed: int,
    requested: int, phase: str, evidence_hashes: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    has_table = gateway.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='generation_timings'"
    ).fetchone() is not None
    rows = gateway.execute(
        'SELECT generation,start_utc,end_utc,evidence_hash FROM generation_timings '
        'WHERE session_id=? ORDER BY generation', (session_id,),
    ).fetchall() if has_table else []
    durations: dict[int, float] = {}
    pending_seconds: float | None = None
    for row in rows:
        gen = row['generation']
        if type(gen) is not int or gen < 1 or gen > requested:
            raise TimingEvidenceError('GENERATION_TIMING_RANGE')
        start = _time(row['start_utc'])
        finish = row['end_utc']
        if gen <= completed:
            # A committed generation can remain unmeasured after a crash until
            # S7 is repaired; never turn incomplete observations into metrics.
            if finish is None:
                continue
            if row['evidence_hash'] != evidence_hashes[gen-1]:
                raise TimingEvidenceError('GENERATION_TIMING_EVIDENCE_MISMATCH')
            end = _time(finish)
            seconds = (end - start).total_seconds()
            if seconds < 0:
                raise TimingEvidenceError('NEGATIVE_GENERATION_DURATION')
            durations[gen] = round(seconds, 2)
        elif gen == completed + 1 and phase in ('AWAITING_DIAGNOSIS', 'RUNNING'):
            if finish is not None or row['evidence_hash'] is not None:
                raise TimingEvidenceError('PENDING_GENERATION_HAS_FINISHED_TIME')
            pending_seconds = round(max(0.0, (datetime.now(timezone.utc)-start).total_seconds()), 2)
        else:
            raise TimingEvidenceError('UNEXPECTED_GENERATION_TIMING')
    average = round(sum(durations.values()) / len(durations), 2) if durations else None
    # ChatGPT is an external caller. No progress clock can predict user/model wait.
    timing = {
        'measured_generations': len(durations),
        'average_seconds': average,
        'current_generation': completed + 1 if completed < requested else None,
        'current_elapsed_seconds': pending_seconds,
        'next_generation_eta_seconds': None,
        'eta_reason': (
            'COMPLETED' if completed >= requested else
            'AWAITING_EXTERNAL_MODEL' if phase in ('AWAITING_PLAN','AWAITING_DIAGNOSIS') else
            'UNVERIFIED_EXECUTION_STATE'
        ),
        'scope': 'OBSERVED_PLAN_TO_S7_WALL_CLOCK_INCLUDES_EXTERNAL_WAIT',
    }
    return timing, [
        {'generation': i, 'duration_seconds': durations.get(i),
         'timing_status': 'MEASURED' if i in durations else 'NOT_RECORDED'}
        for i in range(1, completed + 1)
    ]
