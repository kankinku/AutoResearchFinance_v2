"""Offline comparison of two locally replay-verified Nasdaq capture vintages.

Inputs are externally fetched public quotes saved with local capture timestamps,
not third-party signed *historical as-of* records. This yields evidence of observed
revisions between captures, never retrospective availability or PIT certification.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash
from research.indicator_engine.capture_integrity import verify_nasdaq_capture
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.snapshot_revisions import compare_collected_market_snapshots

PairStatus = Literal["HISTORICAL_ROWS_REVISED", "OVERLAPPING_ROWS_UNCHANGED"]


@dataclass(frozen=True)
class CapturedPriceVintage:
    parquet_path: Path
    raw_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class VerifiedNasdaqVintagePair:
    status: PairStatus
    earlier_captured_at: str
    later_captured_at: str
    earlier_raw_sha256: str
    later_raw_sha256: str
    earlier_capture_hash: str
    later_capture_hash: str
    comparable_bars: int
    changed_bars: int
    changed_session_dates: tuple[str, ...]
    maximum_relative_difference: float
    pair_hash: str
    independence: Literal["SAME_PROVIDER_LOCAL_CAPTURE_TIMES"] = (
        "SAME_PROVIDER_LOCAL_CAPTURE_TIMES"
    )
    independent_historical_publication_verified: Literal[False] = False
    point_in_time_price_verified: Literal[False] = False
    broker_executable: Literal[False] = False

    def record(self) -> dict[str, object]:
        return {
            "status": self.status,
            "earlier_captured_at": self.earlier_captured_at,
            "later_captured_at": self.later_captured_at,
            "earlier_raw_sha256": self.earlier_raw_sha256,
            "later_raw_sha256": self.later_raw_sha256,
            "earlier_capture_hash": self.earlier_capture_hash,
            "later_capture_hash": self.later_capture_hash,
            "comparable_bars": self.comparable_bars,
            "changed_bars": self.changed_bars,
            "changed_session_dates": list(self.changed_session_dates),
            "maximum_relative_difference": self.maximum_relative_difference,
            "pair_hash": self.pair_hash,
            "independence": self.independence,
            "independent_historical_publication_verified": False,
            "point_in_time_price_verified": False,
            "broker_executable": False,
        }


def compare_verified_nasdaq_vintages(
    earlier: CapturedPriceVintage,
    later: CapturedPriceVintage,
) -> VerifiedNasdaqVintagePair:
    """Replay both source raw bytes, then compare overlapping unchanged-policy bars.

    No local file timestamp or as-of claim establishes the time a historical
    publisher made a price observable. Only within-capture chronology is checked.
    """
    a_paths = tuple(path.resolve() for path in (
        earlier.parquet_path, earlier.raw_path, earlier.manifest_path
    ))
    b_paths = tuple(path.resolve() for path in (
        later.parquet_path, later.raw_path, later.manifest_path
    ))
    if len(set(a_paths + b_paths)) != 6:
        raise ResearchCatalogError("two distinct capture triples are required")
    a = verify_nasdaq_capture(
        earlier.parquet_path, earlier.raw_path, earlier.manifest_path
    )
    b = verify_nasdaq_capture(
        later.parquet_path, later.raw_path, later.manifest_path
    )
    # The verifier validated manifest shape and parsed archived source bytes.
    try:
        old_manifest = json.loads(earlier.manifest_path.read_text(encoding="utf-8"))
        new_manifest = json.loads(later.manifest_path.read_text(encoding="utf-8"))
        old_time = datetime.fromisoformat(old_manifest["captured_at"])
        new_time = datetime.fromisoformat(new_manifest["captured_at"])
        old = ParquetDataProvider.read(earlier.parquet_path)
        new = ParquetDataProvider.read(later.parquet_path)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ResearchCatalogError("vintage capture payload invalid") from exc
    if (
        old_time.tzinfo is None or new_time.tzinfo is None
        or old_time >= new_time
    ):
        raise ResearchCatalogError("capture vintages must have chronological timestamps")
    revision = compare_collected_market_snapshots(old, new)
    if revision.status not in ("HISTORICAL_ROWS_REVISED", "OVERLAPPING_ROWS_UNCHANGED"):
        raise ResearchCatalogError(
            "capture vintages require overlapping comparable Nasdaq daily data"
        )
    # Fingerprint both source capture manifests + replay integrity reports and
    # entire overlapping comparison: a local reproducibility claim, not an
    # independent trusted timestamp or external attestation.
    pair_hash = content_hash({
        "schema": "local-nasdaq-capture-vintage-pair-v1",
        "earlier_manifest_sha256": hashlib.sha256(
            earlier.manifest_path.read_bytes()
        ).hexdigest(),
        "later_manifest_sha256": hashlib.sha256(
            later.manifest_path.read_bytes()
        ).hexdigest(),
        "earlier_capture_hash": a.capture_hash,
        "later_capture_hash": b.capture_hash,
        "revision_comparison_hash": revision.comparison_hash,
    })
    return VerifiedNasdaqVintagePair(
        status=revision.status,
        earlier_captured_at=old_time.isoformat(),
        later_captured_at=new_time.isoformat(),
        earlier_raw_sha256=a.raw_sha256,
        later_raw_sha256=b.raw_sha256,
        earlier_capture_hash=a.capture_hash,
        later_capture_hash=b.capture_hash,
        comparable_bars=revision.comparable_bars,
        changed_bars=revision.changed_bars,
        changed_session_dates=revision.changed_date_examples,
        maximum_relative_difference=revision.maximum_relative_difference,
        pair_hash=pair_hash,
    )
