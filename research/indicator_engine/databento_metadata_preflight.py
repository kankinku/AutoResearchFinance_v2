"""Read-only, entitlement-scoped historical QQQ DATA METADATA probe.

Only fixed GET /v0/metadata endpoints are allowed. No timeseries, batch,
credential persistence, buying, OOS or PIT certification can be triggered.
Data vendor metadata reflects CURRENT vendor claims and revisions, not
independently authenticated prices received before historic decisions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

import httpx

from research.indicator_engine.nyse_public_calendar import _closed_dates

DATASET = "XNAS.ITCH"
SCHEMA = "trades"
SYMBOL = "QQQ"
START = "2020-01-02T00:00:00Z"
END_EXCLUSIVE = "2026-01-01T00:00:00Z"
_HOST = "https://hist.databento.com"
_ENDPOINTS = (
    "/v0/metadata.get_dataset_range",
    "/v0/metadata.get_cost",
    "/v0/metadata.get_dataset_condition",
)

ProbeStatus = Literal[
    "AUTH_REQUIRED", "METADATA_UNAVAILABLE", "ENTITLEMENT_OR_AUTH_DENIED",
    "COVERAGE_MISSING", "QUOTED_COST_INVALID", "DATASET_CONDITION_CONFLICT",
    "DATASET_CONDITION_INCOMPLETE", "METADATA_QUOTED_NOT_PIT",
]


@dataclass(frozen=True)
class DatabentoMetadataProbe:
    status: ProbeStatus
    dataset: str = DATASET
    symbol: str = SYMBOL
    schema: str = SCHEMA
    requested_start: str = START
    requested_end_exclusive: str = END_EXCLUSIVE
    schema_coverage_verified: bool = False
    quoted_cost_usd: float | None = None
    condition_records_inspected: int = 0
    condition_recently_modified: int = 0
    expected_regular_sessions: int = 0
    covered_regular_sessions: int = 0
    missing_regular_session_count: int = 0
    condition_full_regular_session_coverage: bool = False
    # CRITICAL: these are NEVER established by metadata or a cost quote.
    publisher_release_authentication_verified: Literal[False] = False
    licensing_verified: Literal[False] = False
    historical_pit_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status, "dataset": self.dataset, "symbol": self.symbol,
            "schema": self.schema, "requested_start": self.requested_start,
            "requested_end_exclusive": self.requested_end_exclusive,
            "schema_coverage_verified": self.schema_coverage_verified,
            "quoted_cost_usd": self.quoted_cost_usd,
            "condition_records_inspected": self.condition_records_inspected,
            "condition_recently_modified": self.condition_recently_modified,
            "condition_scope": "dataset_level_not_symbol_or_schema_specific",
            "expected_regular_sessions": self.expected_regular_sessions,
            "covered_regular_sessions": self.covered_regular_sessions,
            "missing_regular_session_count": self.missing_regular_session_count,
            "condition_full_regular_session_coverage": (
                self.condition_full_regular_session_coverage
            ),
            "retroactive_revision_alert": (
                "Databento announced XNAS.ITCH historical dataset corrections "
                "effective 2026-10-31, including pre-2023 instrument IDs and "
                "EST after-hours coverage. Recheck archive revisions before and "
                "after cutover; do not infer historical PIT."
            ),
            "quote_is_binding": False,
            "consolidated_us_tape_verified": False,
            "publisher_release_authentication_verified": False,
            "licensing_verified": False,
            "historical_pit_verified": False,
            "broker_executable": False,
        }


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("invalid metadata timestamp")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("missing metadata timezone")
    return stamp.astimezone(timezone.utc)


def probe_qqq_xnas_metadata(
    *,
    api_key: str | None,
    client: httpx.Client | None = None,
) -> DatabentoMetadataProbe:
    """Probe published data scope/cost/revisions for a fixed request, never download.

    No request is made without explicit account key. The caller can inject a
    mock client for tests. API key and error messages are NEVER emitted.
    No account state, source response bytes, or credentials are persisted.
    """
    if not api_key or not api_key.strip():
        return DatabentoMetadataProbe(status="AUTH_REQUIRED")
    owned = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
        )
    try:
        fixed = [
            {"dataset": DATASET},
            {
                "dataset": DATASET, "symbols": SYMBOL, "schema": SCHEMA,
                "start": START, "end": END_EXCLUSIVE,
            },
            {"dataset": DATASET, "start_date": "2020-01-02",
             "end_date": "2025-12-31"},
        ]
        replies = []
        for path, params in zip(_ENDPOINTS, fixed, strict=True):
            try:
                response = client.get(
                    _HOST + path, params=params, auth=(api_key, ""),
                    headers={"Accept": "application/json"},
                )
                if response.status_code in (401, 403):
                    return DatabentoMetadataProbe(status="ENTITLEMENT_OR_AUTH_DENIED")
                if response.status_code != 200 or len(response.content) > 256_000:
                    return DatabentoMetadataProbe(status="METADATA_UNAVAILABLE")
                replies.append(response.json())
            except (httpx.HTTPError, ValueError, TypeError):
                return DatabentoMetadataProbe(status="METADATA_UNAVAILABLE")

        source_range, usd_quote, conditions = replies
        try:
            if not isinstance(source_range, dict):
                raise ValueError("bad range")
            schema_ranges = source_range["schema"]
            schema_range = schema_ranges[SCHEMA]
            earliest = _parse_utc(schema_range["start"])
            latest = _parse_utc(schema_range["end"])
            desired_start, desired_end = _parse_utc(START), _parse_utc(END_EXCLUSIVE)
            fully_covered = earliest <= desired_start and latest >= desired_end
            if not fully_covered:
                return DatabentoMetadataProbe(status="COVERAGE_MISSING")
            if (
                not isinstance(usd_quote, (int, float)) or isinstance(usd_quote, bool)
                or not math.isfinite(usd_quote) or usd_quote < 0
            ):
                return DatabentoMetadataProbe(status="QUOTED_COST_INVALID")
            if not isinstance(conditions, list) or not conditions or len(conditions) > 2500:
                return DatabentoMetadataProbe(status="DATASET_CONDITION_CONFLICT")
            # A partial vendor condition array is NOT evidence that all six
            # years were available. Use our independently pinned public NYSE
            # closure calendar to enumerate expected regular session dates.
            # Data quality is dataset-wide; the QQQ symbol still needs separate
            # market records and provider-specific historical PIT validation.
            closure_dates = _closed_dates()
            first_day, last_day = date(2020, 1, 2), date(2025, 12, 31)
            regular = {
                first_day + timedelta(days=n)
                for n in range((last_day - first_day).days + 1)
                if (first_day + timedelta(days=n)).weekday() < 5
                and (first_day + timedelta(days=n)) not in closure_dates
            }
            recently_modified = 0
            seen: set[date] = set()
            available: set[date] = set()
            conflict = False
            for item in conditions:
                if not isinstance(item, dict):
                    conflict = True
                    break
                item_date = item.get("date")
                state = item.get("condition")
                if not isinstance(item_date, str) or state not in (
                    "available", "degraded", "pending", "missing"
                ):
                    conflict = True
                    break
                day = date.fromisoformat(item_date)
                if day < first_day or day > last_day or day in seen:
                    conflict = True
                    break
                seen.add(day)
                modified_at = item.get("last_modified_date")
                if state == "missing":
                    if modified_at is not None:
                        conflict = True
                        break
                elif not isinstance(modified_at, str):
                    conflict = True
                    break
                else:
                    modified = date.fromisoformat(modified_at)
                    if modified.year >= 2026:
                        recently_modified += 1
                if day in regular:
                    if state != "available":
                        conflict = True
                        break
                    available.add(day)
            missing = regular - available
            if conflict:
                return DatabentoMetadataProbe(
                    status="DATASET_CONDITION_CONFLICT",
                    schema_coverage_verified=True,
                    quoted_cost_usd=float(usd_quote),
                    condition_records_inspected=len(conditions),
                    condition_recently_modified=recently_modified,
                    expected_regular_sessions=len(regular),
                    covered_regular_sessions=len(available),
                    missing_regular_session_count=len(missing),
                )
            return DatabentoMetadataProbe(
                status=(
                    "DATASET_CONDITION_INCOMPLETE" if missing
                    else "METADATA_QUOTED_NOT_PIT"
                ),
                schema_coverage_verified=True,
                quoted_cost_usd=float(usd_quote),
                condition_records_inspected=len(conditions),
                condition_recently_modified=recently_modified,
                expected_regular_sessions=len(regular),
                covered_regular_sessions=len(available),
                missing_regular_session_count=len(missing),
                condition_full_regular_session_coverage=not missing,
            )
        except (TypeError, ValueError, KeyError, OverflowError):
            return DatabentoMetadataProbe(status="METADATA_UNAVAILABLE")
    finally:
        if owned:
            client.close()
