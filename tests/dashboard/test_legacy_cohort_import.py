"""Fresh research workspaces must not need a historical October session to collect tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_legacy_cohort_operator_import_does_not_load_historical_controller() -> None:
    project = Path(__file__).resolve().parents[2]
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import scripts.run_academic_cohort as module; "
                "assert callable(module.run); "
                "assert 'scripts.fresh_development_cohort_controller_20261021' "
                "not in sys.modules"
            ),
        ],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stderr
