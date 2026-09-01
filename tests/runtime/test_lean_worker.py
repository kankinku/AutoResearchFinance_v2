from __future__ import annotations

from pathlib import Path

import pytest

from runtime.lean_worker import LeanWorkerSpec, validate_worker_spec


def test_worker_spec_requires_read_only_data_and_unique_output(tmp_path: Path) -> None:
    spec = LeanWorkerSpec(tmp_path / "data", tmp_path / "runs" / "E000001", data_read_only=True)

    validate_worker_spec(spec)
    assert spec.output_dir.name == "E000001"

    with pytest.raises(PermissionError, match="read-only"):
        validate_worker_spec(LeanWorkerSpec(spec.data_dir, spec.output_dir, data_read_only=False))
