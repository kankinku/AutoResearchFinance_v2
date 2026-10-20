"""P5 Pine source-output comparison with externally claimed chart-export CSV.

This module is a fail-closed, read-only mathematical comparator, NOT a Pine
interpreter, source-authentication mechanism, production FeatureRegistry or
S7 backtest. A self-generated fixture can pass numeric comparison but NEVER
claim independent TradingView parity or permit feature promotion.
"""
from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from math import isclose, isfinite
from typing import Literal

from core.data.contracts import DataZone, MarketDataSet
from research.pine_import.boswaves_bridge import _BOSWAVES_UPLOAD_SHA256
from research.pine_import.boswaves_ribbon import compute_ribbon
from research.pine_import.shaakuni_bridge import _SOURCE_UPLOAD
from research.pine_import.shaakuni_order_blocks import compute_shaakuni

PineName = Literal["boswaves", "shaakuni"]
_STATUS = Literal["NUMERIC_MATCH_ONLY_UNAUTHENTICATED", "MISMATCH"]
_SOURCE_PINS = {
    "boswaves": _BOSWAVES_UPLOAD_SHA256,
    "shaakuni": _SOURCE_UPLOAD,
}
_BASE_FIELDS = ("timestamp", "open", "high", "low", "close")
_FEATURE_FIELDS: dict[str, tuple[str, ...]] = {
    "boswaves": (
        "alma", "deviation", "atr", "slope", "trend", "flip",
        "conviction", "ribbon_edge", "ribbon_mid",
        "stopped_now", "new_target_hits",
    ),
    "shaakuni": (
        "atr", "pdh", "pdl", "pwh", "pwl", "created_bull",
        "created_bear", "fresh_bull", "fresh_bear", "mitigated",
    ),
}
_INT_FIELDS = {
    "trend", "flip", "stopped_now", "new_target_hits",
    "created_bull", "created_bear", "fresh_bull", "fresh_bear", "mitigated",
}
_MAX_MISMATCHES = 30
_MAX_CSV_BYTES = 24_000_000


class PineReferenceError(ValueError):
    """Reference file, origin assertion, or data alignment is invalid."""


@dataclass(frozen=True)
class PineReferenceMismatch:
    row: int
    field: str
    expected: float | int | None
    observed: float | int | None


@dataclass(frozen=True)
class PineReferenceComparison:
    indicator: PineName
    source_archive_sha256: str
    dataset_hash: str
    reference_csv_sha256: str
    reference_origin_claim: str
    compared_rows: int
    mismatch_count: int
    first_mismatches: tuple[PineReferenceMismatch, ...]
    status: _STATUS
    independent_tradingview_origin_authenticated: Literal[False] = False
    full_pine_parity_approved: Literal[False] = False
    operational_feature_promotion_allowed: Literal[False] = False


def source_pin_for(indicator: str) -> str:
    """Hash of original *uploaded source archive*, NOT raw .pine bytecode."""
    try:
        return _SOURCE_PINS[indicator]
    except KeyError as exc:
        raise PineReferenceError("unapproved Pine reference indicator") from exc


def _dataset_checked(dataset: MarketDataSet) -> None:
    if dataset.zone != DataZone.DEVELOPMENT:
        raise PineReferenceError("source reference comparison requires DEVELOPMENT zone")
    if dataset.calendar != "us_equities" or dataset.timeframe != "1d":
        raise PineReferenceError("daily US equity review only")
    if not 40 <= len(dataset.bars) <= 50_000:
        raise PineReferenceError("invalid warmup length or memory bound")
    if len({b.symbol for b in dataset.bars}) != 1:
        raise PineReferenceError("mixed symbols are not aligned")
    times = [b.timestamp for b in dataset.bars]
    if any(t.tzinfo is None or t.utcoffset() is None for t in times):
        raise PineReferenceError("timezone-aware market timestamps required")
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise PineReferenceError("non-increasing market timestamps")


def _expected(dataset: MarketDataSet, indicator: PineName) -> list[dict[str, object]]:
    bars = dataset.bars
    opened = tuple(float(b.open) for b in bars)
    high = tuple(float(b.high) for b in bars)
    low = tuple(float(b.low) for b in bars)
    close = tuple(float(b.close) for b in bars)
    if indicator == "boswaves":
        calculated = compute_ribbon(high, low, close)
        details: list[dict[str, object]] = [
            {
                "alma": b.alma,
                "deviation": b.deviation,
                "atr": b.atr,
                "slope": b.slope,
                "trend": b.trend,
                "flip": b.flip,
                "conviction": b.conviction,
                "ribbon_edge": b.ribbon_edge,
                "ribbon_mid": b.ribbon_mid,
                "stopped_now": int(b.stopped_now),
                "new_target_hits": len(b.newly_hit_targets),
            }
            for b in calculated.bars
        ]
    else:
        calculated_sha = compute_shaakuni(
            tuple(b.timestamp for b in bars), opened, high, low, close
        )
        details = [
            {
                "atr": b.atr,
                "pdh": b.levels.previous_day_high,
                "pdl": b.levels.previous_day_low,
                "pwh": b.levels.previous_week_high,
                "pwl": b.levels.previous_week_low,
                "created_bull": int(bool(b.created_bull_ids)),
                "created_bear": int(bool(b.created_bear_ids)),
                "fresh_bull": b.fresh_bull,
                "fresh_bear": b.fresh_bear,
                "mitigated": len(b.mitigated_ids),
            }
            for b in calculated_sha.bars
        ]
    return [
        {
            "timestamp": bar.timestamp.isoformat(),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            **payload,
        }
        for bar, payload in zip(bars, details, strict=True)
    ]


def export_expected_columns_for_fixture(
    dataset: MarketDataSet, indicator: PineName
) -> list[dict[str, object]]:
    """Synthetic test scaffolding only, NEVER third-party parity evidence."""
    _dataset_checked(dataset)
    source_pin_for(indicator)
    return _expected(dataset, indicator)


def _decode_number(raw: str, *, is_int: bool, field: str) -> float | int | None:
    if raw.strip().lower() in ("", "na"):
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise PineReferenceError(f"non-numeric chart value in {field}") from exc
    if not isfinite(value):
        raise PineReferenceError(f"non-finite chart value in {field}")
    if is_int:
        if value != int(value):
            raise PineReferenceError(f"non-integral chart event in {field}")
        return int(value)
    return value


def compare_pine_reference(
    dataset: MarketDataSet,
    manifest: Mapping[str, str],
    csv_bytes: bytes,
    *,
    abs_tolerance: float = 1e-8,
    relative_tolerance: float = 1e-8,
) -> PineReferenceComparison:
    """Compare claimed TradingView CSV to native causal vectors one bar at a time.

    CSV requires normalized timezone-aware ISO-8601 timestamps and exact OHLC
    for the *same* development dataset; missing columns/bars, invalid numbers,
    hashes, or misaligned timestamps are fatal. A numeric PASS is explicitly
    never independent TradingView source authentication or P5 full parity.
    """
    _dataset_checked(dataset)
    indicator_value = manifest.get("indicator", "")
    if indicator_value not in ("boswaves", "shaakuni"):
        raise PineReferenceError("unapproved indicator")
    indicator: PineName = (
        "boswaves" if indicator_value == "boswaves" else "shaakuni"
    )
    pin = source_pin_for(indicator)
    if manifest.get("original_upload_sha256") != pin:
        raise PineReferenceError("original Pine upload hash not pinned")
    if manifest.get("dataset_hash") != dataset.dataset_hash:
        raise PineReferenceError("market snapshot hash mismatch")
    origin = manifest.get("claimed_export_origin", "")
    if not isinstance(origin, str) or not origin.strip():
        raise PineReferenceError("reference origin claim required")
    if not isinstance(csv_bytes, bytes) or len(csv_bytes) > _MAX_CSV_BYTES:
        raise PineReferenceError("reference CSV missing or exceeds memory bound")
    digest = hashlib.sha256(csv_bytes).hexdigest()
    if manifest.get("reference_csv_sha256") != digest:
        raise PineReferenceError("reference CSV SHA-256 mismatch")
    if (
        type(abs_tolerance) not in (float, int)
        or type(relative_tolerance) not in (float, int)
        or not (0 <= abs_tolerance <= 1e-4 and 0 <= relative_tolerance <= 1e-4)
        or not isfinite(abs_tolerance)
        or not isfinite(relative_tolerance)
    ):
        raise PineReferenceError("comparison tolerance must be finite and bounded")
    try:
        content = csv_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
        actual_fields = reader.fieldnames or []
        required = (*_BASE_FIELDS, *_FEATURE_FIELDS[indicator])
        if len(set(actual_fields)) != len(actual_fields) or set(actual_fields) != set(required):
            raise PineReferenceError("reference CSV header fields missing, unknown, or repeated")
        records = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise PineReferenceError("malformed UTF-8 chart export CSV") from exc
    if len(records) != len(dataset.bars):
        raise PineReferenceError("chart export row count does not equal dataset")
    expected = _expected(dataset, indicator)
    mismatches: list[PineReferenceMismatch] = []
    count = 0
    for idx, (observed, ground) in enumerate(zip(records, expected, strict=True)):
        if None in observed or any(v is None for v in observed.values()):
            raise PineReferenceError("extra, missing, or malformed chart CSV columns")
        try:
            timestamp = datetime.fromisoformat(observed["timestamp"])
        except (ValueError, TypeError) as exc:
            raise PineReferenceError("chart timestamps must be ISO-8601") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise PineReferenceError("chart timestamps must have explicit UTC offsets")
        if timestamp != dataset.bars[idx].timestamp:
            raise PineReferenceError("chart bar timestamp mismatch or duplicate/reorder")
        for field in (*_BASE_FIELDS[1:], *_FEATURE_FIELDS[indicator]):
            measured = _decode_number(
                observed[field], is_int=field in _INT_FIELDS, field=field
            )
            value = ground[field]
            if value is not None and not isinstance(value, (float, int)):
                raise PineReferenceError("internal numeric observation contract violated")
            if field in _BASE_FIELDS:
                if measured is None or value is None or not isclose(
                    measured, float(value), rel_tol=1e-10, abs_tol=1e-8
                ):
                    raise PineReferenceError("chart OHLC differs from hashed market data")
                continue
            good = (
                (measured is None and value is None)
                or (
                    measured is not None and value is not None
                    and (
                        measured == value if field in _INT_FIELDS else isclose(
                            measured, float(value),
                            abs_tol=abs_tolerance, rel_tol=relative_tolerance,
                        )
                    )
                )
            )
            if not good:
                count += 1
                if len(mismatches) < _MAX_MISMATCHES:
                    mismatches.append(PineReferenceMismatch(
                        idx, field, value if isinstance(value, (int, float)) else None,
                        measured,
                    ))
    return PineReferenceComparison(
        indicator=indicator,
        source_archive_sha256=pin,
        dataset_hash=dataset.dataset_hash,
        reference_csv_sha256=digest,
        reference_origin_claim=origin,
        compared_rows=len(records),
        mismatch_count=count,
        first_mismatches=tuple(mismatches),
        status="MISMATCH" if count else "NUMERIC_MATCH_ONLY_UNAUTHENTICATED",
    )
