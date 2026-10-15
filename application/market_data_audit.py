"""Read-only reproducibility and pricing checks; never certify historical PIT.

Historical provider corrections and retroactive dividend adjustments cannot be
proved as-of using the current EOD API response. Matching vendor records or
locally pinned hashes are *not* independent historical publication evidence.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import cast

from application.market_data_service import (
    _MARKET_FILENAME,
    MarketDataError,
    MarketDataService,
)
from core.data.contracts import DataZone, MarketDataSet
from core.data.parquet import ParquetDataProvider
from core.data.quality import market_data_quality
from orchestration.evidence import require_research_zone
from research.indicator_engine.nyse_public_calendar import verify_published_nyse_regular_sessions
from research.indicator_engine.validation_gate import inspect_us_equity_daily_observations

_PRICE_TOLERANCE = 0.005  # 0.5% relative discrepancy; comparison, not certification
_ADJUSTMENT_TOLERANCE = 0.003  # 0.3% factor tolerance for rounded price feeds


class MarketDataAuditService:
    """Audit only approved managed development Parquet, without re-fetching it."""

    def __init__(self, project_root: Path, *, state_dir: Path) -> None:
        self.root = project_root.resolve()
        self.state_dir = state_dir.resolve()
        self.market = MarketDataService(self.root)
        self.database = self.state_dir / "system" / "market-data-snapshot-pins.sqlite"

    def _connect(self) -> sqlite3.Connection:
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE IF NOT EXISTS pins("
            "path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, dataset_hash TEXT NOT NULL,"
            "pinned_at TEXT NOT NULL)"
        )
        return db

    def _existing_pin(self, path: str) -> sqlite3.Row | None:
        if not self.database.is_file():
            return None
        with self._connect() as db:
            return cast(
                sqlite3.Row | None,
                db.execute("SELECT * FROM pins WHERE path=?", (path,)).fetchone(),
            )

    def _load(self, path: str) -> tuple[str, Path, MarketDataSet]:
        candidate = self.market._dataset_path(path)
        # File extension/path check does not convey permission to inspect sealed data.
        try:
            require_research_zone(candidate)
            dataset = ParquetDataProvider.read(candidate)
            self.market._check_dataset_identity(candidate, dataset)
        except MarketDataError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise MarketDataError(
                "INVALID_DATASET", "Managed development dataset is invalid."
            ) from exc
        if DataZone(dataset.zone) is not DataZone.DEVELOPMENT:
            raise MarketDataError("DATA_ZONE_DENIED", "Only development data may be audited.")
        return candidate.relative_to(self.root).as_posix(), candidate, dataset

    @staticmethod
    def _sha(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _ratio_close(a: float, b: float, *, tolerance: float) -> bool:
        return abs(a - b) <= tolerance * max(abs(a), abs(b), 1e-12)

    @classmethod
    def _compare_raw(cls, first: MarketDataSet, second: MarketDataSet) -> dict[str, object]:
        p, q = first.provenance, second.provenance
        if p is None or q is None or p.source_id == q.source_id:
            return {
                "status": "NOT_INDEPENDENT",
                "independent_vendors": False,
                "compared_bars": 0,
                "mismatched_bars": 0,
            }
        a = {(bar.symbol, bar.timestamp): bar for bar in first.bars}
        b = {(bar.symbol, bar.timestamp): bar for bar in second.bars}
        if (
            p.corporate_action_policy != "raw"
            or q.corporate_action_policy != "raw"
            or a.keys() != b.keys()
        ):
            return {
                "status": "NONCOMPARABLE_DATA",
                "independent_vendors": True,
                "compared_bars": len(a.keys() & b.keys()),
                "mismatched_bars": 0,
            }
        mismatches = sum(
            not all(
                cls._ratio_close(
                    getattr(a[key], field), getattr(b[key], field), tolerance=_PRICE_TOLERANCE
                )
                for field in ("open", "high", "low", "close")
            )
            for key in a
        )
        return {
            "status": "MATCH" if not mismatches else "PRICE_MISMATCH",
            "independent_vendors": True,
            "compared_bars": len(a),
            "mismatched_bars": mismatches,
            "comparison_basis": "raw_daily_ohlc",
            "tolerance_relative": _PRICE_TOLERANCE,
            "independently_pit_verified": False,
        }

    @classmethod
    def _compare_adjusted(cls, raw: MarketDataSet, adjusted: MarketDataSet) -> dict[str, object]:
        p, q = raw.provenance, adjusted.provenance
        a = {(bar.symbol, bar.timestamp): bar for bar in raw.bars}
        b = {(bar.symbol, bar.timestamp): bar for bar in adjusted.bars}
        if (
            p is None
            or q is None
            or p.source_id != q.source_id
            or p.corporate_action_policy != "raw"
            or q.corporate_action_policy != "total_return_adjusted"
            or a.keys() != b.keys()
        ):
            return {
                "status": "NONCOMPARABLE_DATA",
                "compared_bars": len(a.keys() & b.keys()),
                "mismatched_bars": 0,
            }
        mismatches = 0
        for key, source in a.items():
            target = b[key]
            factors = [
                getattr(target, field) / getattr(source, field)
                for field in ("open", "high", "low", "close")
            ]
            if any(
                not cls._ratio_close(value, factors[-1], tolerance=_ADJUSTMENT_TOLERANCE)
                for value in factors[:-1]
            ):
                mismatches += 1
        return {
            "status": "PRICE_FACTORS_CONSISTENT" if not mismatches else "ADJUSTMENT_MISMATCH",
            "compared_bars": len(a),
            "mismatched_bars": mismatches,
            "tolerance_relative": _ADJUSTMENT_TOLERANCE,
            "independently_corporate_actions_verified": False,
            "note": "Factor consistency does not independently verify dividends, splits, or PIT.",
        }

    def audit(
        self,
        path: str,
        *,
        comparison_path: str | None = None,
        adjusted_path: str | None = None,
    ) -> dict[str, object]:
        # Resolve paths and zone before inspecting contents, then check previous pin
        # even when a subsequent file corruption makes Parquet unreadable.
        source = self.market._dataset_path(path)
        # First detect drift against an earlier validated/pinned file. A changed
        # footer can make the Parquet metadata unreadable; never lose that
        # explicit FILE_CHANGED signal or deserialize corrupted rows.
        relative = source.relative_to(self.root).as_posix()
        actual_sha = self._sha(source)
        pin = self._existing_pin(relative)
        pin_status = (
            "NOT_PINNED"
            if pin is None
            else "MATCHED"
            if pin["sha256"] == actual_sha
            else "FILE_CHANGED"
        )
        if pin_status == "FILE_CHANGED":
            return {
                "data_path": relative,
                "status": "INTEGRITY_FAILED",
                "file_sha256": actual_sha,
                "pin_status": pin_status,
                "blocking_reasons": ["pinned_snapshot_changed"],
                "point_in_time_independently_verified": False,
                "orders_enabled": False,
            }

        _relative, _source, dataset = self._load(relative)
        provenance = dataset.provenance
        quality = market_data_quality(dataset)
        exchange = inspect_us_equity_daily_observations(dataset)
        filename = _MARKET_FILENAME.fullmatch(source.name)
        if filename is None:
            raise MarketDataError("INVALID_DATASET", "Managed dataset filename is invalid.")
        try:
            calendar = verify_published_nyse_regular_sessions(
                dataset,
                requested_start=date.fromisoformat(filename.group("start")),
                requested_end=date.fromisoformat(filename.group("end")),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise MarketDataError(
                "CALENDAR_REFERENCE_INVALID", "Pinned exchange calendar cannot be verified."
            ) from exc
        reasons = list(quality.issues)
        if exchange.weekend_bars:
            reasons.append("weekend_exchange_session_bar")
        if exchange.repeated_session_dates:
            reasons.append("repeated_exchange_session_date")
        if not calendar.regular_session_schedule_matched:
            reasons.append("pinned_official_exchange_session_mismatch_or_unavailable")
            reasons.append("independent_exchange_session_calendar_missing")
        reasons.append("independent_historical_as_of_snapshots_missing")
        independent = None
        if comparison_path is not None:
            _name, _file, other = self._load(comparison_path)
            independent = self._compare_raw(dataset, other)
            if independent["status"] != "MATCH":
                reasons.append("independent_vendor_price_match_unavailable")
        adjusted = None
        if adjusted_path is not None:
            _name, _file, adj = self._load(adjusted_path)
            adjusted = self._compare_adjusted(dataset, adj)
            if adjusted["status"] != "PRICE_FACTORS_CONSISTENT":
                reasons.append("adjusted_price_factors_unverified")
        return {
            "data_path": relative,
            "status": "RESEARCH_ONLY_NOT_PIT_VERIFIED",
            "dataset_hash": dataset.dataset_hash,
            "file_sha256": actual_sha,
            "dataset_version": dataset.version,
            "zone": DataZone(dataset.zone).value,
            "bars": len(dataset.bars),
            "start": dataset.bars[0].timestamp.date().isoformat() if dataset.bars else None,
            "end": dataset.bars[-1].timestamp.date().isoformat() if dataset.bars else None,
            "source_id": provenance.source_id if provenance else None,
            "retrieved_at": provenance.retrieved_at.isoformat() if provenance else None,
            "revision_policy": provenance.revision_policy if provenance else None,
            "corporate_action_policy": provenance.corporate_action_policy if provenance else None,
            "corporate_action_reference": provenance.corporate_action_reference
            if provenance
            else None,
            "quality": quality.record(),
            "exchange_session_observations": exchange.record(),
            "official_nyse_regular_sessions": calendar.record(),
            "pin_status": pin_status,
            "independent_vendor_comparison": independent,
            "corporate_action_consistency": adjusted,
            "blocking_reasons": sorted(set(reasons)),
            "point_in_time_independently_verified": False,
            "orders_enabled": False,
        }

    def pin(self, path: str) -> dict[str, object]:
        """Record first-observed local bytes; detect later changes, not historical releases."""
        report = self.audit(path)
        if report["pin_status"] == "FILE_CHANGED":
            raise MarketDataError("DATA_SNAPSHOT_CHANGED", "Pinned research data file changed.")
        relative = report["data_path"]
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO pins VALUES(?,?,?,?)",
                (
                    relative,
                    report["file_sha256"],
                    report["dataset_hash"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            pinned = db.execute("SELECT * FROM pins WHERE path=?", (relative,)).fetchone()
        if (
            pinned is None
            or pinned["sha256"] != report["file_sha256"]
            or pinned["dataset_hash"] != report["dataset_hash"]
        ):
            raise MarketDataError("DATA_SNAPSHOT_CHANGED", "Pinned research data file changed.")
        return self.audit(path)
