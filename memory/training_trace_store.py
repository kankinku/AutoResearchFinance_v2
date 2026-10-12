"""Immutable development/train-only return traces and exact-prefix cross-run alignment.

These files live in runtime state, never Git. Evidence references their SHA-256
content address. They do NOT provide global DSR approval or PIT verification.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from pathlib import Path

from evaluation.trial_dependence import CohortDependenceReport, estimate_cohort_dependence
from memory.evidence_store import EvidenceIntegrityError, digest, encode

_MAX_CANDIDATES = 128
_MAX_BARS = 100_000
_MAX_BYTES = 24_000_000


@dataclass(frozen=True)
class CandidateTrainingReturns:
    semantic_strategy_hash: str
    returns: tuple[float, ...]


@dataclass(frozen=True)
class TrainingTrace:
    dataset_hash: str
    timeframe: str
    calendar: str
    timestamps: tuple[str, ...]
    candidates: tuple[CandidateTrainingReturns, ...]


@dataclass(frozen=True)
class AlignedTrainingReport:
    status: str
    aligned_observations: int = 0
    candidate_evaluation_instances: int = 0
    unique_semantic_candidates: int = 0
    duplicate_semantic_instances: int = 0
    training_cutoff_at: str | None = None
    cohort_dependence: CohortDependenceReport | None = None
    dsr_approved: bool = False


def _validate(trace: TrainingTrace) -> None:
    if not all(isinstance(s, str) and s for s in (
        trace.dataset_hash, trace.timeframe, trace.calendar,
    )):
        raise EvidenceIntegrityError("invalid training source identity")
    if not 1 <= len(trace.candidates) <= _MAX_CANDIDATES:
        raise EvidenceIntegrityError("invalid training candidate count")
    if not 1 <= len(trace.timestamps) <= _MAX_BARS:
        raise EvidenceIntegrityError("invalid training trace length")
    prior: datetime | None = None
    for label in trace.timestamps:
        try:
            parsed = datetime.fromisoformat(label)
        except (TypeError, ValueError) as exc:
            raise EvidenceIntegrityError("invalid training timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise EvidenceIntegrityError("training timestamps require timezone")
        if prior is not None and parsed <= prior:
            raise EvidenceIntegrityError("training timestamps must increase")
        prior = parsed
    seen: set[str] = set()
    for candidate in trace.candidates:
        semantic = candidate.semantic_strategy_hash
        if not isinstance(semantic, str) or not semantic:
            raise EvidenceIntegrityError("missing semantic identity")
        if semantic in seen:
            raise EvidenceIntegrityError("duplicate semantic identity in one attempt")
        seen.add(semantic)
        if len(candidate.returns) != len(trace.timestamps):
            raise EvidenceIntegrityError("misaligned training return history")
        if any(not isfinite(value) or value < -1 for value in candidate.returns):
            raise EvidenceIntegrityError("training return values must be finite and >= -1")


class TrainingTraceStore:
    """Immutable content-addressed files: readers never create directories."""

    def __init__(self, state_dir: Path) -> None:
        self.folder = state_dir / "system" / "training-traces"

    def _path(self, reference: str) -> Path:
        if (
            not isinstance(reference, str) or len(reference) != 64
            or any(ch not in "0123456789abcdef" for ch in reference)
        ):
            raise EvidenceIntegrityError("invalid training trace reference")
        return self.folder / f"{reference}.json"

    def write(self, trace: TrainingTrace) -> str:
        _validate(trace)
        payload = asdict(trace)
        serialized = encode(payload).encode("utf-8")
        if len(serialized) > _MAX_BYTES:
            raise EvidenceIntegrityError("training trace exceeds storage bound")
        reference = digest(payload)
        path = self._path(reference)
        self.folder.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if self.read(reference) != trace:
                raise EvidenceIntegrityError("training trace conflict") from None
            return reference
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(serialized)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            raise EvidenceIntegrityError("training trace write failed") from exc
        return reference

    def read(self, reference: str) -> TrainingTrace:
        path = self._path(reference)
        if path.is_symlink() or not path.is_file():
            raise EvidenceIntegrityError("invalid or missing training trace")
        if path.stat().st_size > _MAX_BYTES:
            raise EvidenceIntegrityError("training trace too large")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise EvidenceIntegrityError("invalid training trace JSON") from exc
        if not isinstance(payload, dict) or digest(payload) != reference:
            raise EvidenceIntegrityError("training trace checksum mismatch")
        try:
            expected = TrainingTrace(
                dataset_hash=payload["dataset_hash"],
                timeframe=payload["timeframe"],
                calendar=payload["calendar"],
                timestamps=tuple(payload["timestamps"]),
                candidates=tuple(
                    CandidateTrainingReturns(
                        semantic_strategy_hash=item["semantic_strategy_hash"],
                        returns=tuple(item["returns"]),
                    )
                    for item in payload["candidates"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceIntegrityError("invalid training trace structure") from exc
        _validate(expected)
        if json.loads(encode(asdict(expected))) != payload:
            raise EvidenceIntegrityError("unexpected training trace attributes")
        return expected


def align_training_traces(traces: tuple[TrainingTrace, ...]) -> AlignedTrainingReport:
    """Only identical start-to-cutoff timebases from one source; never fill gaps."""
    if not traces:
        return AlignedTrainingReport("NO_OBSERVED_TRACES")
    for trace in traces:
        _validate(trace)
    count = sum(len(item.candidates) for item in traces)
    def fail(status: str) -> AlignedTrainingReport:
        return AlignedTrainingReport(status, candidate_evaluation_instances=count)

    keys = {(item.dataset_hash, item.timeframe, item.calendar) for item in traces}
    if len(keys) != 1:
        return fail("INCOMPARABLE_SOURCE")
    cutoff_count = min(len(item.timestamps) for item in traces)
    if cutoff_count < 30:
        return fail("INSUFFICIENT_ALIGNED_HISTORY")
    times = traces[0].timestamps[:cutoff_count]
    if any(item.timestamps[:cutoff_count] != times for item in traces):
        return fail("INCOMPARABLE_TIMEBASE")
    distinct: dict[str, tuple[float, ...]] = {}
    for trace in traces:
        for item in trace.candidates:
            row = item.returns[:cutoff_count]
            prior = distinct.get(item.semantic_strategy_hash)
            if prior is not None and prior != row:
                return fail("INCONSISTENT_SEMANTIC_RETURNS")
            distinct[item.semantic_strategy_hash] = row
    if len(distinct) > _MAX_CANDIDATES:
        return fail("COHORT_LIMIT_EXCEEDED")
    if len(distinct) < 2:
        return fail("INSUFFICIENT_INDEPENDENT_CANDIDATES")
    diagnosis = estimate_cohort_dependence(
        tuple(distinct[identifier] for identifier in sorted(distinct)),
        training_cutoff_at=times[-1],
    )
    if diagnosis.status != "ESTIMATED_TRAIN_ONLY_COHORT":
        return fail(diagnosis.status)
    return AlignedTrainingReport(
        "ALIGNED_TRAIN_ONLY",
        cutoff_count, count, len(distinct), count - len(distinct),
        times[-1], diagnosis,
    )
