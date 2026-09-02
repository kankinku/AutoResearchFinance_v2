from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash
from strategy_import.fingerprint import classify_duplicate, strategy_fingerprint
from strategy_import.models import AnalysisResult
from strategy_ir.schema import Provenance, StrategyIR


@dataclass(frozen=True)
class CatalogRecord:
    record_id: str
    status: str
    source: dict[str, Any]
    strategy_id: str | None
    strategy_hash: str | None
    semantic_fingerprint: str | None
    duplicate_kind: str
    duplicate_of: str | None
    reason: str
    profile: dict[str, Any]
    strategy: dict[str, Any] | None


class StrategyRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.imported_dir = root / "imported"
        self.normalized_dir = root / "normalized"
        self.catalog_path = root / "catalog.json"
        self.imported_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_dir.mkdir(parents=True, exist_ok=True)

    def register(
        self, analysis: AnalysisResult, *, source_path: Path, source_origin: str
    ) -> CatalogRecord:
        catalog = self._read_catalog()
        source_hash = analysis.source_hash
        strategy = analysis.strategy if isinstance(analysis.strategy, StrategyIR) else None
        strategy = (
            _canonicalize_strategy(strategy, source_path, source_hash, analysis.source_type)
            if strategy is not None
            else None
        )
        for index, raw in enumerate(catalog):
            if raw.get("source", {}).get("source_hash") == source_hash:
                if strategy is not None:
                    raw["source"] = {
                        "origin": source_origin,
                        "source_path": source_path.as_posix(),
                        "source_hash": source_hash,
                        "source_type": analysis.source_type,
                    }
                    raw["strategy"] = strategy.model_dump(mode="json", by_alias=True)
                    raw["strategy_hash"] = content_hash(
                        strategy.model_dump(mode="json", by_alias=True, exclude={"provenance"})
                    )
                    raw["semantic_fingerprint"] = strategy_fingerprint(strategy)
                    self._atomic_json(self.imported_dir / f"{raw['record_id']}.json", raw)
                    self._atomic_json(
                        self.normalized_dir / f"{raw['record_id']}.json",
                        strategy.model_dump(mode="json", by_alias=True),
                    )
                    catalog[index] = raw
                    self._atomic_json(self.catalog_path, {"schema_version": 1, "records": catalog})
                return _record_from_dict(raw)

        existing = [
            StrategyIR.model_validate(raw["strategy"])
            for raw in catalog
            if isinstance(raw.get("strategy"), dict)
        ]
        duplicate = classify_duplicate(strategy, existing) if strategy is not None else None
        record = CatalogRecord(
            record_id=f"{source_hash[:16]}-{len(catalog) + 1}",
            status=analysis.status.value,
            source={
                "origin": source_origin,
                "source_path": source_path.as_posix(),
                "source_hash": source_hash,
                "source_type": analysis.source_type,
            },
            strategy_id=strategy.strategy_id if strategy is not None else None,
            strategy_hash=content_hash(
                strategy.model_dump(mode="json", by_alias=True, exclude={"provenance"})
            )
            if strategy is not None
            else None,
            semantic_fingerprint=strategy_fingerprint(strategy) if strategy is not None else None,
            duplicate_kind=duplicate.kind if duplicate is not None else "NOT_APPLICABLE",
            duplicate_of=duplicate.duplicate_of if duplicate is not None else None,
            reason=analysis.reason,
            profile=analysis.profile,
            strategy=strategy.model_dump(mode="json", by_alias=True)
            if strategy is not None
            else None,
        )
        self._atomic_json(self.imported_dir / f"{record.record_id}.json", asdict(record))
        if strategy is not None:
            self._atomic_json(
                self.normalized_dir / f"{record.record_id}.json",
                strategy.model_dump(mode="json", by_alias=True),
            )
        catalog.append(asdict(record))
        self._atomic_json(self.catalog_path, {"schema_version": 1, "records": catalog})
        return record

    def records(self) -> list[CatalogRecord]:
        return [_record_from_dict(raw) for raw in self._read_catalog()]

    def _read_catalog(self) -> list[dict[str, Any]]:
        if not self.catalog_path.is_file():
            return []
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        records = payload.get("records", [])
        return records if isinstance(records, list) else []

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)


def _record_from_dict(raw: dict[str, Any]) -> CatalogRecord:
    return CatalogRecord(
        record_id=str(raw.get("record_id", "")),
        status=str(raw.get("status", "UNSUPPORTED")),
        source=dict(raw.get("source", {})),
        strategy_id=raw.get("strategy_id"),
        strategy_hash=raw.get("strategy_hash"),
        semantic_fingerprint=raw.get("semantic_fingerprint"),
        duplicate_kind=str(raw.get("duplicate_kind", "NOT_APPLICABLE")),
        duplicate_of=raw.get("duplicate_of"),
        reason=str(raw.get("reason", "")),
        profile=dict(raw.get("profile", {})),
        strategy=raw.get("strategy") if isinstance(raw.get("strategy"), dict) else None,
    )


def _canonicalize_strategy(
    strategy: StrategyIR, source_path: Path, source_hash: str, source_type: str
) -> StrategyIR:
    return strategy.model_copy(
        update={
            "provenance": Provenance(
                source_path=source_path.as_posix(),
                source_hash=source_hash,
                source_type=source_type,
            )
        }
    )
