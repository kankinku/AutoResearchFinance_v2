from __future__ import annotations

import json
from pathlib import Path

from strategy_import.pipeline import import_local_source


def _preset(strategy_id: str) -> str:
    return f"""
class Preset:
    builder_state = {{
        'metadata': {{'id': '{strategy_id}', 'category': 'trend'}},
        'indicators': [
            {{'indicatorId': 'sma', 'alias': 'fast', 'params': {{'period': 5}}}},
            {{'indicatorId': 'sma', 'alias': 'slow', 'params': {{'period': 20}}}},
        ],
        'entry': {{'logic': 'AND', 'conditions': [{{
            'left': {{'type': 'indicator', 'indicatorAlias': 'fast'}},
            'operator': 'cross_above',
            'right': {{'type': 'indicator', 'indicatorAlias': 'slow'}},
        }}]}},
        'exit': {{'logic': 'OR', 'conditions': [{{
            'left': {{'type': 'indicator', 'indicatorAlias': 'fast'}},
            'operator': 'cross_below',
            'right': {{'type': 'indicator', 'indicatorAlias': 'slow'}},
        }}]}},
        'risk': {{'stopLoss': {{'enabled': True, 'percent': 5}},
                 'takeProfit': {{'enabled': True, 'percent': 10}}}},
    }}
"""


def test_all_ten_kis_builder_presets_use_the_same_pipeline(tmp_path: Path) -> None:
    preset_dir = tmp_path / "strategy_builder" / "strategy_core" / "preset"
    preset_dir.mkdir(parents=True)
    for index in range(1, 11):
        (preset_dir / f"strategy_{index:02d}.py").write_text(
            _preset(f"kis_{index:02d}"), encoding="utf-8"
        )

    summary = import_local_source(
        tmp_path,
        strategies_dir=tmp_path / "strategies",
        source_origin="KIS",
        kis_presets=True,
    )

    assert summary.scanned == 10
    assert summary.normalized == 10
    assert summary.review_required == 0
    assert len(summary.records) == 10
    assert (tmp_path / "strategies" / "catalog.json").is_file()
    catalog = json.loads((tmp_path / "strategies" / "catalog.json").read_text(encoding="utf-8"))
    assert all(
        not str(record["strategy"]["provenance"]["source_path"]).startswith("C:/")
        for record in catalog["records"]
    )
