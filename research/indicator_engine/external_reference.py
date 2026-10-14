"""Allowlisted pandas numerical cross-check for S6 research-only primitives.

No third-party source code is vendored or evaluated dynamically. The canonical
trade engine always uses reviewed internal signal functions; this is only a
separate computation/reference gate before an indicator may be VERIFIED.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from importlib.metadata import version
from typing import Any, Literal

import pandas as pd  # type: ignore[import-untyped]

from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalog, ResearchCatalogError
from research.indicator_engine.models import IndicatorCandidate
from research.indicator_engine.s6_seed import S6_SIGNALS
from research.indicator_engine.signals import _synthetic_prices, calculate_signal

_ALLOWLIST = {signal.signal_id: signal for signal in S6_SIGNALS}


class ReferenceBackendError(ValueError):
    """A provider or numerical reference did not pass the strict S6 audit."""


@dataclass(frozen=True)
class ExternalReferenceReport:
    signal_id: str
    candidate_hash: str
    backend: Literal["pandas"]
    version: str
    license: Literal["BSD-3-Clause"]
    source: str
    fixtures_verified: tuple[str, ...]
    prefix_consistency: bool
    borderline_binary_count: int
    result_hash: str
    passed: Literal[True] = True
    research_only: Literal[True] = True


def _backend_version() -> str:
    return version("pandas")


def _pandas_reference(
    candidate: IndicatorCandidate, obs: dict[str, tuple[float, ...]],
) -> tuple[float | None, ...]:
    n = candidate.lookback
    close = pd.Series(obs["close"], dtype="float64")
    size = len(close)
    out: list[float | None] = [None] * size
    kind = candidate.calculator
    if kind == "sma_pullback":
        avg = close.rolling(n, min_periods=n).mean()
        for t in range(n - 1, size):
            out[t] = float(close.iloc[t] < avg.iloc[t])
    elif kind == "dual_sma_trend":
        fast = max(2, n // 4)
        short = close.rolling(fast, min_periods=fast).mean()
        long = close.rolling(n, min_periods=n).mean()
        for t in range(n - 1, size):
            out[t] = float(short.iloc[t] > long.iloc[t])
    elif kind == "ema_direction":
        if size >= n:
            initial = float(close.iloc[:n].mean())
            seeded = pd.Series([initial, *obs["close"][n:]], dtype="float64")
            ema = seeded.ewm(alpha=2.0 / (n + 1.0), adjust=False).mean()
            for t in range(n - 1, size):
                out[t] = float(close.iloc[t] > ema.iloc[t - n + 1])
    elif kind == "range_low_reclaim":
        low = pd.Series(obs["low"], dtype="float64")
        previous = low.rolling(n, min_periods=n).min().shift(1)
        for t in range(n, size):
            level = float(previous.iloc[t])
            out[t] = float(low.iloc[t] < level and close.iloc[t] > level)
    else:
        raise ReferenceBackendError("not approved S6 reference calculator")
    return tuple(out)


def _fixtures() -> tuple[tuple[str, dict[str, tuple[float, ...]]], ...]:
    original = _synthetic_prices()
    flat = tuple(100.0 for _ in range(530))
    choppy = tuple(90.0 + (i % 19 - 9) * 0.3 + i * 0.018 for i in range(530))
    return (
        ("synthetic_trend", original),
        ("flat", {"close": flat, "low": tuple(v - 1 for v in flat)}),
        ("choppy", {"close": choppy, "low": tuple(v - 1.5 for v in choppy)}),
    )


def audit_s6_external_reference(candidate: IndicatorCandidate) -> ExternalReferenceReport:
    """Match entire reference vectors on three differently shaped bounded inputs."""
    # model_copy() can bypass Pydantic validation: reparse before invoking pandas.
    try:
        candidate = IndicatorCandidate.model_validate(candidate.model_dump(mode="json"))
    except ValueError as exc:
        raise ReferenceBackendError("not approved S6 indicator metadata") from exc
    approved = _ALLOWLIST.get(candidate.signal_id)
    if approved is None or (
        candidate.model_copy(update={"status": "PROPOSED"}) != approved
    ):
        raise ReferenceBackendError("not approved S6 indicator identity")
    backend_version = _backend_version()
    major_str = backend_version.split(".", 1)[0]
    if not major_str.isdigit() or int(major_str) not in (2, 3):
        raise ReferenceBackendError("unsupported pandas backend version")
    evaluated: list[dict[str, Any]] = []
    borderline = 0
    for name, prices in _fixtures():
        internal = calculate_signal(candidate, prices)
        external = _pandas_reference(candidate, prices)
        if len(external) != len(internal):
            raise ReferenceBackendError("S6 independent reference mismatch")
        for i, (left, right) in enumerate(zip(internal, external, strict=True)):
            if left == right:
                continue
            # Strict binary comparisons of near-identical floating-point
            # rolling means can disagree at machine epsilon. Record the
            # ambiguity explicitly; large-margin disagreements always fail.
            if candidate.calculator != "dual_sma_trend":
                raise ReferenceBackendError("S6 independent reference mismatch")
            c = prices["close"]
            from statistics import fmean
            fast = max(2, candidate.lookback // 4)
            if i < candidate.lookback - 1:
                raise ReferenceBackendError("S6 warmup reference mismatch")
            fast_avg = fmean(c[i - fast + 1:i + 1])
            slow_avg = fmean(c[i - candidate.lookback + 1:i + 1])
            if abs(fast_avg - slow_avg) > 1e-12 * max(1.0, abs(c[i])):
                raise ReferenceBackendError("S6 independent reference mismatch")
            borderline += 1
        for t in (candidate.lookback, candidate.lookback + 1, 250, len(internal) - 1):
            if t <= len(internal):
                truncated = {field: data[:t] for field, data in prices.items()}
                prefix = _pandas_reference(candidate, truncated)
                if prefix != external[:t]:
                    raise ReferenceBackendError("pandas causal prefix mismatch")
        if any(x is not None and (not math.isfinite(x) or x not in (0.0, 1.0))
               for x in external):
            raise ReferenceBackendError("nonbinary S6 output")
        evaluated.append({"fixture": name, "output": external})
    signature = content_hash(candidate.model_dump(mode="json", exclude={"status"}))
    digest = content_hash({
        "schema": "s6-pandas-external-reference-v1",
        "candidate_hash": signature, "backend_version": backend_version,
        "fixtures": evaluated,
        "borderline_binary_count": borderline,
    })
    return ExternalReferenceReport(
        signal_id=candidate.signal_id,
        candidate_hash=signature,
        backend="pandas", version=backend_version,
        license="BSD-3-Clause", source="https://github.com/pandas-dev/pandas",
        fixtures_verified=tuple(name for name, _ in _fixtures()),
        prefix_consistency=True, borderline_binary_count=borderline, result_hash=digest,
    )


def _create_audit_table(catalog: ResearchCatalog) -> None:
    with catalog._connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS s6_external_provenance (
            signal_id TEXT PRIMARY KEY,
            report_json TEXT NOT NULL,
            report_hash TEXT NOT NULL
        )''')


def get_s6_external_reference(
    catalog: ResearchCatalog, signal_id: str,
) -> ExternalReferenceReport | None:
    _create_audit_table(catalog)
    with catalog._connect() as db:
        row = db.execute(
            'SELECT report_json,report_hash FROM s6_external_provenance WHERE signal_id=?',
            (signal_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        obj = json.loads(row["report_json"])
        if content_hash(obj) != row["report_hash"]:
            raise ResearchCatalogError("external provenance integrity mismatch")
        if not isinstance(obj.get("fixtures_verified"), list):
            raise ResearchCatalogError("external provenance integrity mismatch")
        record = ExternalReferenceReport(
            **{**obj, "fixtures_verified": tuple(obj["fixtures_verified"])}
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise ResearchCatalogError("external provenance integrity mismatch") from exc
    if (record.signal_id != signal_id or record.backend != "pandas"
            or record.license != "BSD-3-Clause" or not record.passed):
        raise ResearchCatalogError("external provenance integrity mismatch")
    return record


def capture_s6_external_reference(
    catalog: ResearchCatalog, report: ExternalReferenceReport,
) -> bool:
    indicator = catalog.get_indicator(report.signal_id)
    if not report.passed or indicator.signal_id not in _ALLOWLIST:
        raise ResearchCatalogError("invalid S6 external provenance")
    digest = content_hash(indicator.model_dump(mode="json", exclude={"status"}))
    if digest != report.candidate_hash:
        raise ResearchCatalogError("S6 signal identity differs from external provenance")
    previous = get_s6_external_reference(catalog, report.signal_id)
    if previous is not None:
        if previous != report:
            raise ResearchCatalogError("external provenance integrity conflict")
        return False
    payload = asdict(report)
    with catalog._connect() as db:
        db.execute(
            'INSERT INTO s6_external_provenance(signal_id,report_json,report_hash) '
            'VALUES(?,?,?)',
            (report.signal_id, json.dumps(payload, sort_keys=True), content_hash(payload)),
        )
    return True
