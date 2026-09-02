from __future__ import annotations

import json
from pathlib import Path

from strategy_import.analyzers import analyze_python_source
from strategy_import.registry import StrategyRegistry


def test_registry_persists_normalized_ir_and_catalog(tmp_path: Path) -> None:
    source = tmp_path / "golden_cross.py"
    source.write_text(
        """
class Preset:
    builder_state = {
        'metadata': {'id': 'golden_cross', 'category': 'trend'},
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
    analysis = analyze_python_source(source)
    registry = StrategyRegistry(tmp_path / "strategies")

    record = registry.register(analysis, source_path=source, source_origin="local")

    assert record.status == "NORMALIZED"
    assert (tmp_path / "strategies" / "normalized").is_dir()
    assert json.loads((tmp_path / "strategies" / "catalog.json").read_text(encoding="utf-8"))[
        "records"
    ]


def test_registry_keeps_review_required_analysis(tmp_path: Path) -> None:
    source = tmp_path / "dynamic.py"
    source.write_text("raise RuntimeError('never execute')\n", encoding="utf-8")
    analysis = analyze_python_source(source)

    record = StrategyRegistry(tmp_path / "strategies").register(
        analysis, source_path=source, source_origin="local"
    )

    assert record.status == "REVIEW_REQUIRED"
    assert record.profile["detected_constructs"] == ["python_module"]


def test_registry_refreshes_provenance_for_idempotent_reimport(tmp_path: Path) -> None:
    source = tmp_path / "preset.py"
    source.write_text(
        """
class Preset:
    builder_state = {
        'metadata': {'id': 'stable', 'category': 'trend'},
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
    analysis = analyze_python_source(source)
    registry = StrategyRegistry(tmp_path / "strategies")
    registry.register(analysis, source_path=Path("temporary/preset.py"), source_origin="clone")

    refreshed = registry.register(
        analysis, source_path=Path("preset/preset.py"), source_origin="clone@commit"
    )

    assert refreshed.strategy is not None
    assert refreshed.strategy["provenance"]["source_path"] == "preset/preset.py"
