from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.integrity.hashes import content_hash
from strategy_import.pipeline import import_local_source
from strategy_import.sources import CloneManager, parse_github_source
from strategy_ir.normalizer import ImportStatus, normalize_source

_ALLOWED_SOURCE_SUFFIXES = frozenset(
    {".py", ".yaml", ".yml", ".json", ".pine", ".pinescript"}
)


class StrategyService:
    """Static strategy inspection/import without executing external source."""

    def __init__(
        self,
        *,
        project_root: Path,
        clone_manager: CloneManager | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.clone_manager = clone_manager or CloneManager()

    def validate(self, source_path: str) -> dict[str, object]:
        source = self._project_path(source_path, require_exists=True)
        if not source.is_file() or source.suffix.lower() not in _ALLOWED_SOURCE_SUFFIXES:
            raise PermissionError("strategy source is not an allowed file")
        result = normalize_source(source)
        payload: dict[str, object] = {
            "status": "VALID" if result.status is ImportStatus.NORMALIZED else result.status.value,
            "source_hash": result.source_hash,
            "source_type": result.source_type,
            "reason": result.reason,
        }
        if result.strategy is not None:
            payload["strategy_id"] = result.strategy.strategy_id
            payload["strategy_hash"] = content_hash(
                result.strategy.model_dump(mode="json", by_alias=True)
            )
        return payload

    def import_strategies(
        self,
        *,
        source_path: str | None = None,
        repository_url: str | None = None,
        ref: str = "main",
        strategies_dir: str = "strategies",
        dry_run: bool = True,
        kis_presets: bool = False,
    ) -> dict[str, Any]:
        if bool(source_path) == bool(repository_url):
            raise ValueError("provide exactly one of source_path or repository_url")
        destination = self._project_path(strategies_dir, require_exists=False)
        if destination == self.project_root:
            raise PermissionError("strategies_dir cannot be the project root")

        if repository_url is not None:
            github_source = parse_github_source(repository_url, ref=ref)
            summary = import_local_source(
                self.project_root,
                strategies_dir=destination,
                source_origin=github_source.repository_url,
                github_source=github_source,
                dry_run=dry_run,
                kis_presets=kis_presets,
                clone_manager=self.clone_manager,
            )
        else:
            assert source_path is not None
            source = self._project_path(source_path, require_exists=True)
            summary = import_local_source(
                source,
                strategies_dir=destination,
                dry_run=dry_run,
                kis_presets=kis_presets,
            )
        payload = summary.as_dict()
        payload["status"] = "DRY_RUN" if dry_run else "IMPORTED"
        payload["orders_enabled"] = False
        return payload

    def list_strategies(self, *, strategies_dir: str = "strategies") -> dict[str, object]:
        destination = self._project_path(strategies_dir, require_exists=False)
        catalog_path = destination / "catalog.json"
        if not catalog_path.is_file():
            return {"status": "OK", "count": 0, "records": []}
        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("strategy catalog is invalid") from exc
        raw_records = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(raw_records, list):
            raise ValueError("strategy catalog records are invalid")

        records: list[dict[str, object]] = []
        for raw in raw_records:
            if not isinstance(raw, dict):
                continue
            source = raw.get("source", {})
            safe_source = (
                {
                    key: value
                    for key, value in source.items()
                    if key in {"origin", "source_path", "source_hash", "source_type"}
                }
                if isinstance(source, dict)
                else {}
            )
            records.append(
                {
                    "record_id": str(raw.get("record_id", "")),
                    "status": str(raw.get("status", "UNSUPPORTED")),
                    "strategy_id": raw.get("strategy_id"),
                    "strategy_hash": raw.get("strategy_hash"),
                    "duplicate_kind": str(raw.get("duplicate_kind", "NOT_APPLICABLE")),
                    "duplicate_of": raw.get("duplicate_of"),
                    "reason": str(raw.get("reason", "")),
                    "source": safe_source,
                }
            )
        return {"status": "OK", "count": len(records), "records": records}

    def _project_path(self, value: str, *, require_exists: bool) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("project path is required")
        candidate = (self.project_root / value).resolve()
        if candidate != self.project_root and self.project_root not in candidate.parents:
            raise PermissionError("path is outside project root")
        if require_exists and not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate
