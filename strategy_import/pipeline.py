from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from strategy_import.analyzers import analyze_source_file
from strategy_import.models import AnalysisStatus, GitHubSource
from strategy_import.registry import CatalogRecord, StrategyRegistry
from strategy_import.sources import CloneManager, iter_safe_source_files


@dataclass(frozen=True)
class ImportSummary:
    scanned: int
    normalized: int
    review_required: int
    unsupported: int
    exact_duplicates: int
    partial_duplicates: int
    records: list[CatalogRecord]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["records"] = [
            {
                "record_id": record.record_id,
                "status": record.status,
                "strategy_id": record.strategy_id,
                "duplicate_kind": record.duplicate_kind,
                "duplicate_of": record.duplicate_of,
                "reason": record.reason,
            }
            for record in self.records
        ]
        return payload


def import_local_source(
    source: Path,
    *,
    strategies_dir: Path,
    source_origin: str = "local",
    github_source: GitHubSource | None = None,
    dry_run: bool = False,
    kis_presets: bool = False,
    clone_manager: CloneManager | None = None,
) -> ImportSummary:
    root = source.resolve()
    temporary_root: Path | None = None
    commit = None
    if github_source is not None:
        if clone_manager is None:
            clone_manager = CloneManager()
        root, commit = clone_manager.clone(github_source)
        temporary_root = root
    try:
        files = _candidate_files(root, kis_presets=kis_presets)
        registry = StrategyRegistry(strategies_dir) if not dry_run else None
        records: list[CatalogRecord] = []
        counts = {status: 0 for status in AnalysisStatus}
        exact = 0
        partial = 0
        for path in files:
            analysis = analyze_source_file(path)
            counts[analysis.status] += 1
            if dry_run:
                continue
            assert registry is not None
            record = registry.register(
                analysis,
                source_path=_relative_or_absolute(path, root),
                source_origin=source_origin if commit is None else f"{source_origin}@{commit}",
            )
            records.append(record)
            if record.duplicate_kind == "EXACT_DUPLICATE":
                exact += 1
            elif record.duplicate_kind == "PARTIAL_DUPLICATE":
                partial += 1
        return ImportSummary(
            scanned=len(files),
            normalized=counts[AnalysisStatus.NORMALIZED],
            review_required=counts[AnalysisStatus.REVIEW_REQUIRED],
            unsupported=counts[AnalysisStatus.UNSUPPORTED],
            exact_duplicates=exact,
            partial_duplicates=partial,
            records=records,
        )
    finally:
        if temporary_root is not None:
            import shutil

            shutil.rmtree(temporary_root, ignore_errors=True)


def _candidate_files(root: Path, *, kis_presets: bool) -> list[Path]:
    files = iter_safe_source_files(root)
    if kis_presets:
        files = [
            item
            for item in files
            if item.relative_path.as_posix().startswith("strategy_builder/strategy_core/preset/")
            and item.relative_path.name != "__init__.py"
        ]
    elif root.is_file():
        return [root]
    else:
        files = [
            item
            for item in files
            if any(
                marker in item.content
                for marker in ("STRATEGY", "builder_state", "StrategyDefinition", "@register")
            )
        ]
    return [item.path for item in files]


def _relative_or_absolute(path: Path, root: Path) -> Path:
    if root.is_dir():
        try:
            return path.relative_to(root)
        except ValueError:
            pass
    return path
