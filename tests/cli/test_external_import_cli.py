from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_import_strategies_persists_local_kis_style_source(tmp_path: Path) -> None:
    source = tmp_path / "preset.py"
    source.write_text(
        """
class Preset:
    builder_state = {
        'metadata': {'id': 'cli-kis', 'category': 'trend'},
        'indicators': [
            {'indicatorId': 'sma', 'alias': 'fast', 'params': {'period': 5}},
            {'indicatorId': 'sma', 'alias': 'slow', 'params': {'period': 20}},
        ],
        'entry': {'logic': 'AND', 'conditions': [{
            'left': {'type': 'indicator', 'indicatorAlias': 'fast'},
            'operator': 'cross_above',
            'right': {'type': 'indicator', 'indicatorAlias': 'slow'},
        }]},
        'exit': {'logic': 'OR', 'conditions': [{
            'left': {'type': 'indicator', 'indicatorAlias': 'fast'},
            'operator': 'cross_below',
            'right': {'type': 'indicator', 'indicatorAlias': 'slow'},
        }]},
        'risk': {
            'stopLoss': {'enabled': True, 'percent': 5},
            'takeProfit': {'enabled': True, 'percent': 10},
        },
    }
""",
        encoding="utf-8",
    )
    target = tmp_path / "strategies"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "cli.py"),
            "import-strategies",
            "--source",
            str(source),
            "--strategies-dir",
            str(target),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["normalized"] == 1
    catalog = json.loads((target / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["records"][0]["strategy_id"] == "cli-kis"


def test_import_strategies_dry_run_does_not_write_catalog(tmp_path: Path) -> None:
    source = tmp_path / "preset.py"
    source.write_text("class Preset: pass\n", encoding="utf-8")
    target = tmp_path / "strategies"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "cli.py"),
            "import-strategies",
            "--source",
            str(source),
            "--strategies-dir",
            str(target),
            "--dry-run",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["review_required"] == 1
    assert not (target / "catalog.json").exists()
