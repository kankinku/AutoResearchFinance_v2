from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LeanWorkerSpec:
    data_dir: Path
    output_dir: Path
    data_read_only: bool = True


def validate_worker_spec(spec: LeanWorkerSpec) -> None:
    if not spec.data_read_only:
        raise PermissionError("worker market data mount must be read-only")
    if not spec.data_dir:
        raise ValueError("worker data directory is required")
    if not spec.output_dir.name:
        raise ValueError("worker output directory must be unique")
    if spec.data_dir.resolve() == spec.output_dir.resolve():
        raise ValueError("worker data and output directories must be separate")
