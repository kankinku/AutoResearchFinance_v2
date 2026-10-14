"""Offline integrity replay for retained Nasdaq OHLC source bytes, never PIT proof."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from core.data.parquet import ParquetDataProvider
from core.integrity.hashes import content_hash
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_capture import parse_nasdaq_qqq

_MAX_MANIFEST = 16384
_MAX_RAW = 3000000


@dataclass(frozen=True)
class CaptureIntegrityAudit:
    dataset_hash: str
    raw_sha256: str
    capture_hash: str
    verified_rows: int
    status: Literal["LOCAL_CAPTURE_BYTES_VERIFIED"] = "LOCAL_CAPTURE_BYTES_VERIFIED"
    point_in_time_verified: Literal[False] = False
    independent_benchmark_verified: Literal[False] = False
    candidate_promotable: Literal[False] = False


def verify_nasdaq_capture(
    parquet_path: Path, raw_path: Path, manifest_path: Path
) -> CaptureIntegrityAudit:
    """Reparse preserved source bytes and require exact original manifest identity.

    These checks establish local reproducibility, not data-provider
    independence, historical release times or authenticated exchange values.
    """
    if any(not p.is_file() for p in (parquet_path, raw_path, manifest_path)):
        raise ResearchCatalogError("capture files missing")
    if manifest_path.stat().st_size > _MAX_MANIFEST or raw_path.stat().st_size > _MAX_RAW:
        raise ResearchCatalogError("capture evidence exceeds size limit")
    try:
        proof = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(proof, dict) or set(proof) != {
            "dataset_hash", "raw_sha256", "row_count", "captured_at", "source_url",
            "output_path", "raw_path", "manifest_path", "status",
            "point_in_time_verified", "independent_benchmark_verified",
            "candidate_promotable",
        }:
            raise ValueError("manifest shape changed")
        if (
            proof["status"] != "NON_PIT_SOURCE_CAPTURE"
            or proof["point_in_time_verified"] is not False
            or proof["independent_benchmark_verified"] is not False
            or proof["candidate_promotable"] is not False
            or not isinstance(proof["row_count"], int)
            or isinstance(proof["row_count"], bool)
            or proof["row_count"] < 1
        ):
            raise ValueError("capture manifest claims unsupported certification")
        for key, path in (
            ("output_path", parquet_path), ("raw_path", raw_path),
            ("manifest_path", manifest_path),
        ):
            if not isinstance(proof[key], str) or Path(proof[key]).resolve() != path.resolve():
                raise ValueError("capture references unrelated local path")
        url = urlsplit(proof["source_url"])
        fields = parse_qs(url.query, strict_parsing=True)
        if (
            (url.scheme, url.netloc, url.path)
            != ("https", "api.nasdaq.com", "/api/quote/QQQ/historical")
            or url.username is not None or url.password is not None
            or url.fragment or set(fields) != {"assetclass", "fromdate", "todate", "limit"}
            or any(len(value) != 1 for value in fields.values())
            or fields["assetclass"] != ["etf"]
        ):
            raise ValueError("capture URL is unrecognized")
        start, end = date.fromisoformat(fields["fromdate"][0]), date.fromisoformat(
            fields["todate"][0]
        )
        cap = int(fields["limit"][0])
        if not 1 <= cap <= 4000 or proof["row_count"] > cap:
            raise ValueError("capture limit out of bounds")
        captured_at = datetime.fromisoformat(proof["captured_at"])
        raw = raw_path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        if checksum != proof["raw_sha256"]:
            raise ResearchCatalogError("raw digest mismatch")
        rebuilt = parse_nasdaq_qqq(raw, start, end, captured_at)
        if proof["row_count"] != len(rebuilt.bars):
            raise ResearchCatalogError("capture reported row count mismatch")
        if proof["dataset_hash"] != rebuilt.dataset_hash:
            raise ResearchCatalogError("capture dataset digest mismatch")
        try:
            persisted = ParquetDataProvider.read(parquet_path)
        except (OSError, ValueError, TypeError) as exc:
            raise ResearchCatalogError("capture parquet could not be decoded") from exc
        if persisted.dataset_hash != rebuilt.dataset_hash:
            raise ResearchCatalogError("capture parquet mismatches source bytes")
    except ResearchCatalogError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, OSError) as exc:
        raise ResearchCatalogError("capture manifest cannot be verified") from exc
    capture_hash = content_hash({
        "version": "nasdaq-local-capture-integrity-v1",
        "dataset": rebuilt.dataset_hash,
        "raw_sha256": checksum,
        "manifest": proof,
    })
    return CaptureIntegrityAudit(
        dataset_hash=rebuilt.dataset_hash, raw_sha256=checksum,
        capture_hash=capture_hash, verified_rows=len(rebuilt.bars),
    )
